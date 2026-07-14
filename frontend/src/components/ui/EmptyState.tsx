"use client";
interface EmptyStateProps { icon?: React.ReactNode; title: string; description?: string; action?: React.ReactNode; }
export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6 text-center animate-fade-in">
      {icon && <div className="mb-5 text-text-tertiary">{icon}</div>}
      <h3 className="text-[28px] font-semibold text-text-primary mb-2 leading-tight">{title}</h3>
      {description && <p className="text-text-secondary max-w-md mb-8 text-[17px] leading-relaxed">{description}</p>}
      {action}
    </div>
  );
}
