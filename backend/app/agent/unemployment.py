"""
Unemployment and Benefits Fraud Detection Tools.

Specialized tools for detecting fraud in:
- Unemployment insurance claims
- SNAP (food stamps)
- Housing assistance
- General welfare benefits
"""
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from app.agent.base import BaseTool


# ============================================================================
# Output Schemas
# ============================================================================

class SSNValidationOutput(BaseModel):
    """Output from SSN validation check."""
    ssn: str = Field(description="SSN checked (last 4 only)")
    is_valid: bool = Field(description="SSN passes format and checksum validation")
    state_issued: str = Field(description="State where SSN was issued")
    year_issued_range: str = Field(description="Approximate year range SSN was issued")
    is_deceased: bool = Field(description="SSN belongs to deceased individual (DMF check)")
    risk_flag: bool = Field(description="High-risk indicator")
    anomalies: List[str] = Field(default_factory=list, description="List of anomalies found")


class EmployerVerificationOutput(BaseModel):
    """Output from employer verification."""
    employer_name: str
    employer_exists: bool = Field(description="Employer found in state database")
    business_status: str = Field(description="Active, Inactive, or Not Found")
    fein: str = Field(description="Federal Employer Identification Number")
    employees_reported: int = Field(description="Number of employees reported to state")
    last_wage_report: str = Field(description="Date of last quarterly wage report")
    employment_verified: bool = Field(description="Claimant found in wage records")
    risk_flag: bool
    anomalies: List[str] = Field(default_factory=list)


class CrossStateClaimCheckOutput(BaseModel):
    """Output from cross-state claim detection."""
    ssn_last4: str
    states_with_claims: List[str] = Field(description="States where claims detected")
    total_claim_count: int
    concurrent_claims: int = Field(description="Number of overlapping active claims")
    is_multi_state_fraud: bool = Field(description="Same SSN filing in multiple states simultaneously")
    total_weekly_amount: int = Field(description="Sum of all concurrent weekly benefits")
    risk_score: int = Field(ge=0, le=100)
    risk_flag: bool


class PrisonInmateCheckOutput(BaseModel):
    """Output from prison inmate database check."""
    name: str
    dob: str
    ssn_last4: str
    is_incarcerated: bool
    facility_name: str = Field(description="Prison facility if incarcerated")
    facility_state: str
    incarceration_start_date: str
    expected_release_date: str
    inmate_id: str
    risk_flag: bool


class AddressHistoryOutput(BaseModel):
    """Output from address history analysis."""
    current_address: str
    address_tenure_days: int = Field(description="Days at current address")
    previous_addresses: List[Dict[str, str]] = Field(description="Previous addresses")
    address_changes_6mo: int = Field(description="Number of address changes in past 6 months")
    is_fraud_ring_address: bool = Field(description="Address associated with multiple claims")
    claims_at_address: int = Field(description="Number of other claims at this address")
    risk_flag: bool
    anomalies: List[str] = Field(default_factory=list)


# ============================================================================
# Tool Implementations
# ============================================================================

class SSNValidationTool(BaseTool):
    """
    Validates Social Security Number authenticity and checks for deceased individuals.

    Fraud Patterns:
    - SSN belongs to deceased individual (ghost claimant)
    - SSN format invalid or from invalid range
    - SSN issued after claimant's stated DOB
    - SSN flagged in stolen identity database

    Data Sources:
    - SSA Death Master File (DMF)
    - SSN area/group/serial validation
    - Stolen identity databases
    """

    name = "ssn_validation"
    description = "Validates SSN authenticity and checks Death Master File"

    async def execute(
        self,
        ssn: str,
        name: str,
        dob: str
    ) -> SSNValidationOutput:
        """
        Validate SSN against multiple fraud indicators.

        Args:
            ssn: Social Security Number (will be masked in output)
            name: Claimant's name
            dob: Date of birth (YYYY-MM-DD)

        Returns:
            SSNValidationOutput with validation results
        """
        # Mock data with keyword triggers
        ssn_last4 = ssn[-4:] if len(ssn) >= 4 else ssn
        anomalies = []
        risk_flag = False

        # TRIGGER 1: Deceased individual (Death Master File)
        if "deceased" in name.lower() or ssn_last4 in ["9999", "0000"]:
            is_deceased = True
            risk_flag = True
            anomalies.append("SSN matches Death Master File - claimant is deceased")
        else:
            is_deceased = False

        # TRIGGER 2: Invalid SSN format
        if ssn_last4 in ["6666", "1111"]:
            anomalies.append("SSN format invalid or from reserved range")
            risk_flag = True

        # TRIGGER 3: SSN issued after DOB (impossible)
        if "2020" in dob and ssn_last4 in ["2023"]:
            anomalies.append("SSN issued after claimant's date of birth")
            risk_flag = True

        # Mock state/year data
        state_map = {
            "0": "New Hampshire", "1": "New York", "2": "Pennsylvania",
            "3": "California", "4": "Florida", "5": "Texas"
        }
        state_issued = state_map.get(ssn[0] if ssn else "0", "Unknown")
        year_issued_range = "1990-2000" if not is_deceased else "1950-1960"

        is_valid = len(anomalies) == 0

        return SSNValidationOutput(
            ssn=f"***-**-{ssn_last4}",
            is_valid=is_valid,
            state_issued=state_issued,
            year_issued_range=year_issued_range,
            is_deceased=is_deceased,
            risk_flag=risk_flag,
            anomalies=anomalies
        )


class EmployerVerificationTool(BaseTool):
    """
    Verifies claimant's previous employer and employment history.

    Fraud Patterns:
    - Employer does not exist (fake company)
    - Employer never reported claimant in wage records
    - Employer is inactive/dissolved before claimed employment
    - Claimant still employed (ineligible for unemployment)

    Data Sources:
    - State Quarterly Wage Reports
    - Business registry
    - Employer FEIN verification
    """

    name = "employer_verification"
    description = "Verifies previous employer and employment history"

    async def execute(
        self,
        employer_name: str,
        claimant_name: str,
        claimant_ssn: str,
        claimed_termination_date: str
    ) -> EmployerVerificationOutput:
        """
        Verify employer and employment relationship.

        Args:
            employer_name: Name of previous employer
            claimant_name: Claimant's name
            claimant_ssn: Claimant's SSN
            claimed_termination_date: Date claimant says they were terminated

        Returns:
            EmployerVerificationOutput with verification results
        """
        anomalies = []
        risk_flag = False

        # TRIGGER 1: Fake employer (does not exist)
        if "fake" in employer_name.lower() or "fraud" in employer_name.lower():
            employer_exists = False
            business_status = "Not Found"
            employment_verified = False
            employees_reported = 0
            last_wage_report = "Never"
            fein = "00-0000000"
            anomalies.append("Employer not found in state business registry")
            anomalies.append("No wage reports ever filed")
            risk_flag = True
        else:
            # TRIGGER 2: Employer exists but employment not verified
            employer_exists = True
            business_status = "Active"
            fein = "12-3456789"
            employees_reported = 50

            if "verify" in employer_name.lower():
                employment_verified = False
                anomalies.append("Claimant not found in employer's quarterly wage reports")
                risk_flag = True
            else:
                employment_verified = True

            # Calculate last wage report (should be recent)
            today = datetime.now()
            last_quarter = today - timedelta(days=90)
            last_wage_report = last_quarter.strftime("%Y-%m-%d")

        return EmployerVerificationOutput(
            employer_name=employer_name,
            employer_exists=employer_exists,
            business_status=business_status,
            fein=fein,
            employees_reported=employees_reported,
            last_wage_report=last_wage_report,
            employment_verified=employment_verified,
            risk_flag=risk_flag,
            anomalies=anomalies
        )


class CrossStateClaimCheckTool(BaseTool):
    """
    Detects fraudulent claims filed in multiple states simultaneously.

    Fraud Patterns:
    - Same SSN filing in 2+ states at once (impossible)
    - Total weekly benefits exceed legal maximums
    - Fraud rings filing across multiple states

    Data Sources:
    - National unemployment database (SIDES)
    - State-to-state data sharing agreements
    - Neo4j graph analysis (existing tool)
    """

    name = "cross_state_claim_check"
    description = "Detect claims in multiple states simultaneously"

    async def execute(
        self,
        ssn: str,
        name: str,
        current_state: str
    ) -> CrossStateClaimCheckOutput:
        """
        Check for duplicate claims across states.

        Args:
            ssn: Claimant's SSN
            name: Claimant's name
            current_state: State where current claim is filed

        Returns:
            CrossStateClaimCheckOutput with results
        """
        ssn_last4 = ssn[-4:] if len(ssn) >= 4 else ssn

        # TRIGGER: Multi-state fraud (SSN used in multiple states)
        if ssn_last4 in ["5555", "7777"] or "multi" in name.lower():
            states_with_claims = [current_state, "California", "Florida", "Texas"]
            total_claim_count = 4
            concurrent_claims = 4
            is_multi_state_fraud = True
            total_weekly_amount = 400 * 4  # $400/week x 4 states
            risk_score = 100
            risk_flag = True
        else:
            states_with_claims = [current_state]
            total_claim_count = 1
            concurrent_claims = 1
            is_multi_state_fraud = False
            total_weekly_amount = 400
            risk_score = 0
            risk_flag = False

        return CrossStateClaimCheckOutput(
            ssn_last4=ssn_last4,
            states_with_claims=states_with_claims,
            total_claim_count=total_claim_count,
            concurrent_claims=concurrent_claims,
            is_multi_state_fraud=is_multi_state_fraud,
            total_weekly_amount=total_weekly_amount,
            risk_score=risk_score,
            risk_flag=risk_flag
        )


class PrisonInmateCheckTool(BaseTool):
    """
    Checks if claimant is incarcerated (ineligible for benefits).

    Fraud Patterns:
    - Claimant filing while in prison
    - Fraud rings using inmate identities
    - Family members filing on behalf of incarcerated individuals

    Data Sources:
    - State Department of Corrections databases
    - Federal Bureau of Prisons
    - Jail rosters (county level)
    """

    name = "prison_inmate_check"
    description = "Check if claimant is incarcerated"

    async def execute(
        self,
        name: str,
        dob: str,
        ssn: str,
        state: str
    ) -> PrisonInmateCheckOutput:
        """
        Check prison inmate databases.

        Args:
            name: Claimant's name
            dob: Date of birth
            ssn: SSN
            state: State of residence

        Returns:
            PrisonInmateCheckOutput with results
        """
        ssn_last4 = ssn[-4:] if len(ssn) >= 4 else ssn

        # TRIGGER: Inmate found in prison database
        if "inmate" in name.lower() or "prison" in name.lower():
            is_incarcerated = True
            facility_name = f"{state} State Penitentiary"
            facility_state = state
            incarceration_start_date = "2023-01-15"
            expected_release_date = "2026-01-15"
            inmate_id = f"{state.upper()[:2]}{ssn_last4}"
            risk_flag = True
        else:
            is_incarcerated = False
            facility_name = "N/A"
            facility_state = "N/A"
            incarceration_start_date = "N/A"
            expected_release_date = "N/A"
            inmate_id = "N/A"
            risk_flag = False

        return PrisonInmateCheckOutput(
            name=name,
            dob=dob,
            ssn_last4=ssn_last4,
            is_incarcerated=is_incarcerated,
            facility_name=facility_name,
            facility_state=facility_state,
            incarceration_start_date=incarceration_start_date,
            expected_release_date=expected_release_date,
            inmate_id=inmate_id,
            risk_flag=risk_flag
        )


class AddressHistoryTool(BaseTool):
    """
    Analyzes address history for fraud ring indicators.

    Fraud Patterns:
    - Multiple claimants using same address
    - Frequent address changes (address hopping)
    - Address doesn't exist or is commercial property
    - P.O. Box used as residence

    Data Sources:
    - Credit bureau address history
    - USPS change of address database
    - Neo4j graph (detect fraud rings at same address)
    """

    name = "address_history"
    description = "Analyze address history and fraud ring indicators"

    async def execute(
        self,
        current_address: str,
        name: str,
        ssn: str
    ) -> AddressHistoryOutput:
        """
        Analyze address history.

        Args:
            current_address: Current address
            name: Claimant's name
            ssn: SSN

        Returns:
            AddressHistoryOutput with results
        """
        anomalies = []
        risk_flag = False

        # TRIGGER 1: Fraud ring address (multiple claims)
        if "fraud" in current_address.lower() or "ring" in current_address.lower():
            is_fraud_ring_address = True
            claims_at_address = 47
            address_changes_6mo = 0
            address_tenure_days = 180
            anomalies.append("47 other claims filed from this address in past 6 months")
            risk_flag = True
        else:
            # TRIGGER 2: Frequent address changes (address hopping)
            if "hopper" in name.lower():
                address_changes_6mo = 6
                address_tenure_days = 15
                is_fraud_ring_address = False
                claims_at_address = 1
                anomalies.append("6 address changes in past 6 months (address hopping)")
                risk_flag = True
            else:
                address_changes_6mo = 0
                address_tenure_days = 730  # 2 years
                is_fraud_ring_address = False
                claims_at_address = 1

        # Mock previous addresses
        previous_addresses = [
            {"address": "456 Oak St, Anytown, USA", "dates": "2020-2022"},
            {"address": "789 Pine Ave, Somewhere, USA", "dates": "2018-2020"}
        ] if address_changes_6mo == 0 else [
            {"address": "123 Temp Rd", "dates": "2024-10"},
            {"address": "456 Temp Ave", "dates": "2024-09"},
            {"address": "789 Temp Blvd", "dates": "2024-08"}
        ]

        return AddressHistoryOutput(
            current_address=current_address,
            address_tenure_days=address_tenure_days,
            previous_addresses=previous_addresses,
            address_changes_6mo=address_changes_6mo,
            is_fraud_ring_address=is_fraud_ring_address,
            claims_at_address=claims_at_address,
            risk_flag=risk_flag,
            anomalies=anomalies
        )
