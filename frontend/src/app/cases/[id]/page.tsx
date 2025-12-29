'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { caseApi, type CaseDetail, type EvidenceLog } from '@/lib/api';
import { formatDate, getRiskColor, getRiskLevel } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export default function CaseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.id as string;

  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [adjudicating, setAdjudicating] = useState(false);

  useEffect(() => {
    loadCase();
  }, [caseId]);

  const loadCase = async () => {
    try {
      setLoading(true);
      const data = await caseApi.getCase(caseId);
      setCaseData(data);
    } catch (error) {
      console.error('Failed to load case:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAdjudicate = async (status: 'APPROVED' | 'DENIED') => {
    if (!confirm(`Are you sure you want to ${status} this case?`)) {
      return;
    }

    try {
      setAdjudicating(true);
      await caseApi.adjudicate(caseId, { status });
      await loadCase(); // Reload case data
      alert(`Case successfully ${status}`);
    } catch (error) {
      console.error('Failed to adjudicate:', error);
      alert('Failed to adjudicate case');
    } finally {
      setAdjudicating(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center py-12 text-gray-500">Loading case details...</div>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center py-12 text-gray-500">Case not found</div>
      </div>
    );
  }

  const riskColor = getRiskColor(caseData.final_risk_score);
  const riskLevel = getRiskLevel(caseData.final_risk_score);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-6">
        <button
          onClick={() => router.push('/')}
          className="text-blue-600 hover:text-blue-800 mb-4"
        >
          ← Back to Dashboard
        </button>

        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              {caseData.applicant_name || 'Unknown Entity'}
            </h1>
            <p className="text-gray-500 mt-1">Case ID: {caseData.external_ref_id}</p>
          </div>

          {/* Risk Score Badge */}
          <div className="text-center">
            {caseData.final_risk_score !== null ? (
              <>
                <div
                  className={`text-6xl font-bold ${
                    riskColor === 'red'
                      ? 'text-red-600'
                      : riskColor === 'yellow'
                      ? 'text-yellow-600'
                      : 'text-green-600'
                  }`}
                >
                  {caseData.final_risk_score}
                </div>
                <div className="text-sm font-semibold text-gray-600 mt-1">
                  {riskLevel} RISK
                </div>
              </>
            ) : (
              <div className="text-gray-400">Processing...</div>
            )}
          </div>
        </div>
      </div>

      {/* Split Screen Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Left Panel: Application Data */}
        <Card>
          <CardHeader>
            <CardTitle>Application Details</CardTitle>
            <CardDescription>Information submitted by applicant</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="space-y-4">
              <div>
                <dt className="text-sm font-medium text-gray-500">Applicant Name</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {caseData.applicant_name || 'N/A'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Tax ID</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {caseData.applicant_tax_id || 'N/A'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Address</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {caseData.applicant_address || 'N/A'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Status</dt>
                <dd className="mt-1">
                  <Badge>{caseData.status}</Badge>
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Submitted</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {formatDate(caseData.created_at)}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        {/* Right Panel: Agent's Investigation Summary */}
        <Card>
          <CardHeader>
            <CardTitle>AI Investigation Summary</CardTitle>
            <CardDescription>Agent's findings and narrative</CardDescription>
          </CardHeader>
          <CardContent>
            {caseData.summary_narrative ? (
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown>{caseData.summary_narrative}</ReactMarkdown>
              </div>
            ) : (
              <div className="text-gray-500 italic">
                Investigation in progress...
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Evidence Section */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Evidence Collected</CardTitle>
          <CardDescription>
            {caseData.evidence_logs.length} verification{caseData.evidence_logs.length !== 1 ? 's' : ''} performed
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {caseData.evidence_logs.map((evidence: EvidenceLog) => (
              <div
                key={evidence.id}
                className={`border rounded-lg p-4 ${
                  evidence.risk_flag ? 'border-red-300 bg-red-50' : 'border-gray-200'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <h4 className="font-semibold text-gray-900">
                      {evidence.source.replace(/_/g, ' ')}
                    </h4>
                    <p className="text-xs text-gray-500 mt-1">
                      {formatDate(evidence.created_at)}
                    </p>
                  </div>
                  {evidence.risk_flag && (
                    <Badge className="bg-red-100 text-red-800">Risk Flag</Badge>
                  )}
                </div>

                {/* Finding */}
                {evidence.synthesized_finding && (
                  <div className="mb-3">
                    <p className="text-sm text-gray-700">
                      {evidence.synthesized_finding}
                    </p>
                  </div>
                )}

                {/* Image if available (Street View) */}
                {evidence.image_url && (
                  <div className="mb-3">
                    <img
                      src={evidence.image_url}
                      alt="Street View"
                      className="rounded border max-w-full h-auto"
                    />
                  </div>
                )}

                {/* Raw Data (Collapsible) */}
                <details className="mt-2">
                  <summary className="text-xs text-blue-600 cursor-pointer hover:text-blue-800">
                    View Raw Data
                  </summary>
                  <pre className="mt-2 text-xs bg-gray-100 p-2 rounded overflow-x-auto">
                    {JSON.stringify(evidence.raw_data, null, 2)}
                  </pre>
                </details>
              </div>
            ))}

            {caseData.evidence_logs.length === 0 && (
              <div className="text-center py-8 text-gray-500">
                No evidence collected yet
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Adjudication Actions */}
      {caseData.status === 'REVIEW_REQUIRED' && (
        <Card>
          <CardHeader>
            <CardTitle>Adjudication</CardTitle>
            <CardDescription>Make final determination on this case</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex space-x-4">
              <Button
                onClick={() => handleAdjudicate('APPROVED')}
                disabled={adjudicating}
                className="bg-green-600 hover:bg-green-700 text-white"
              >
                Approve
              </Button>

              <Button
                onClick={() => handleAdjudicate('DENIED')}
                disabled={adjudicating}
                variant="destructive"
              >
                Deny
              </Button>

              <Button variant="outline" disabled={adjudicating}>
                Request More Info
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Already Adjudicated */}
      {(caseData.status === 'APPROVED' || caseData.status === 'DENIED') && (
        <Card>
          <CardContent className="py-6">
            <div className="text-center">
              <Badge
                className={
                  caseData.status === 'APPROVED'
                    ? 'bg-green-100 text-green-800 text-lg px-4 py-2'
                    : 'bg-red-100 text-red-800 text-lg px-4 py-2'
                }
              >
                Case {caseData.status}
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
