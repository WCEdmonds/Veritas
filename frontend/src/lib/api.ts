import axios from 'axios';

/**
 * Typed client for the Veritas backend (FastAPI, see backend/app/main.py).
 *
 * Base URL comes from NEXT_PUBLIC_API_URL and defaults to the local backend.
 * The backend's AgencyAuthMiddleware expects an agency token; it is read from
 * NEXT_PUBLIC_AGENCY_TOKEN and defaults to the development token in
 * backend/app/config.py.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const AGENCY_TOKEN = process.env.NEXT_PUBLIC_AGENCY_TOKEN || 'dev-token-12345';

export const http = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${AGENCY_TOKEN}`,
    'X-Agency-Token': AGENCY_TOKEN,
  },
  timeout: 30_000,
});

// ---------------------------------------------------------------------------
// Types mirroring backend/app/schemas.py
// ---------------------------------------------------------------------------

export type CaseStatus =
  | 'NEW'
  | 'PENDING'
  | 'PROCESSING'
  | 'REVIEW_REQUIRED'
  | 'APPROVED'
  | 'DENIED';

export type CaseType = 'GRANT' | 'UNEMPLOYMENT' | 'BENEFITS';

export type VerificationSource = string;

/** Row in the case list (CaseListResponse). */
export interface Case {
  id: string;
  external_ref_id: string;
  applicant_name: string | null;
  status: CaseStatus;
  final_risk_score: number | null;
  created_at: string;
}

/** Evidence entry (EvidenceLogResponse). raw_data is the tool's full output. */
export interface EvidenceLog {
  id: string;
  case_id: string;
  source: VerificationSource;
  raw_data: Record<string, any> | null;
  synthesized_finding: string | null;
  risk_flag: boolean;
  image_url: string | null;
  created_at: string;
}

/** Full case (CaseDetailResponse). */
export interface CaseDetail {
  id: string;
  external_ref_id: string;
  applicant_name: string | null;
  applicant_tax_id: string | null;
  applicant_address: string | null;
  status: CaseStatus;
  final_risk_score: number | null;
  summary_narrative: string | null;
  created_at: string;
  evidence_logs: EvidenceLog[];
}

export interface PaginatedCases {
  items: Case[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface Stats {
  total_cases: number;
  pending_review: number;
  high_risk_cases: number;
  cases_by_status: Record<string, number>;
}

export interface ListCasesParams {
  page?: number;
  page_size?: number;
  status_filter?: CaseStatus;
  min_risk_score?: number;
}

export interface IngestPayload {
  external_ref_id: string;
  applicant_name?: string;
  applicant_tax_id?: string;
  applicant_address?: string;
  case_type?: CaseType;
  [extra: string]: unknown;
}

export interface AdjudicatePayload {
  status: 'APPROVED' | 'DENIED';
  notes?: string;
}

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------

export const caseApi = {
  async listCases(params: ListCasesParams = {}): Promise<PaginatedCases> {
    const { data } = await http.get<PaginatedCases>('/api/v1/cases', { params });
    return data;
  },

  async getCase(caseId: string): Promise<CaseDetail> {
    const { data } = await http.get<CaseDetail>(`/api/v1/cases/${caseId}`);
    return data;
  },

  async getEvidence(caseId: string): Promise<EvidenceLog[]> {
    const { data } = await http.get<EvidenceLog[]>(`/api/v1/cases/${caseId}/evidence`);
    return data;
  },

  async getStats(): Promise<Stats> {
    const { data } = await http.get<Stats>('/api/v1/stats');
    return data;
  },

  async ingest(payload: IngestPayload): Promise<Case> {
    const { data } = await http.post<Case>('/api/v1/ingest', payload);
    return data;
  },

  async adjudicate(caseId: string, payload: AdjudicatePayload): Promise<void> {
    await http.post(`/api/v1/cases/${caseId}/adjudicate`, payload);
  },
};
