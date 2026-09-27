import Check from "@iconify-react/bi/check";

type StepState = "pending" | "active" | "done";

export default function StatusStep({ label, state }: { label: string; state: StepState }) {
  return (
    <div className="flex items-center gap-2 whitespace-nowrap">
      {state === "done" && (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-white">
          <Check className="h-4 w-4" />
        </span>
      )}
      {state === "active" && (
        <span className="flex h-5 w-5 items-center justify-center rounded-full border-2 border-primary border-t-transparent animate-spin" />
      )}
      {state === "pending" && (
        <span className="flex h-5 w-5 items-center justify-center rounded-full border-2 border-neutral-300" />
      )}
      <span className={state === "pending" ? "text-neutral-500" : "text-neutral-900"}>{label}</span>
    </div>
  );
}
