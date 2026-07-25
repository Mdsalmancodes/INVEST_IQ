"use client";

export interface ConfidenceIndicatorProps {
  confidence: number;
  label?: string;
}

function confidenceColorClass(confidence: number): string {
  if (confidence >= 0.7) return "bg-success";
  if (confidence >= 0.4) return "bg-warning";
  return "bg-danger";
}

/**
 * ConfidenceIndicator — a labeled percentage bar rendering the Hybrid
 * Decision Engine's overall_confidence / per-forecast confidence value
 * (Confidence value object, always [0.0, 1.0] — Document 4 §10.4's
 * "Overall Confidence %" requirement).
 */
export function ConfidenceIndicator({ confidence, label = "Confidence" }: ConfidenceIndicatorProps) {
  const percentage = Math.round(confidence * 100);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs text-text-secondary">
        <span>{label}</span>
        <span className="font-medium text-text-primary">{percentage}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="h-2 w-full overflow-hidden rounded-full bg-primary-100"
      >
        <div
          className={`h-full rounded-full ${confidenceColorClass(confidence)}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
