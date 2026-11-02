import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Tailwind class merger used by the UI primitives. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/** Badge classes for a case status (mirrors backend CaseStatus). */
export function getStatusColor(status: string | null | undefined): string {
  switch (status) {
    case 'APPROVED':
      return 'bg-green-100 text-green-800';
    case 'DENIED':
      return 'bg-red-100 text-red-800';
    case 'REVIEW_REQUIRED':
      return 'bg-yellow-100 text-yellow-800';
    case 'PROCESSING':
      return 'bg-blue-100 text-blue-800';
    case 'PENDING':
    case 'NEW':
      return 'bg-gray-100 text-gray-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}

/** Risk colour bucket: green < 40, yellow 40-69, red >= 70. Null scores are grey. */
export function getRiskColor(score: number | null | undefined): 'green' | 'yellow' | 'red' | 'gray' {
  if (score === null || score === undefined) return 'gray';
  if (score >= 70) return 'red';
  if (score >= 40) return 'yellow';
  return 'green';
}

export function getRiskLevel(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'Pending';
  if (score >= 90) return 'Critical';
  if (score >= 70) return 'High';
  if (score >= 40) return 'Medium';
  return 'Low';
}
