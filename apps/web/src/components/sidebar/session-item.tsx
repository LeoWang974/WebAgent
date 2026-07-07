interface SessionItemProps {
  active?: boolean;
  onClick?: () => void;
  status?: string;
  title: string;
}

export function SessionItem({
  active = false,
  onClick,
  status = "active",
  title,
}: SessionItemProps) {
  return (
    <button
      className={`group w-full rounded-md px-2 py-1.5 text-left hover:bg-[#e9e9e2] ${
        active ? "bg-white shadow-sm ring-1 ring-[#deded8]" : ""
      }`}
      onClick={onClick}
      type="button"
    >
      <span className="block truncate text-[13px] leading-5">{title}</span>
      <span className="mt-0.5 flex items-center gap-1.5 text-[11px] capitalize text-muted-foreground">
        <span
          className={`size-1.5 rounded-full ${
            status === "running" ? "bg-amber-500" : "bg-emerald-500"
          }`}
        />
        {status}
      </span>
    </button>
  );
}
