const STATUS_STYLES = {
  pending: "bg-muted text-muted-foreground",
  analyzing: "bg-muted text-muted-foreground",
  ready: "bg-primary/20 text-primary",
  passed: "bg-primary/20 text-primary",
  failed: "bg-red-500/20 text-red-400",
  blocked: "bg-yellow-500/20 text-yellow-400",
};

export default function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || "bg-muted text-muted-foreground";
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
