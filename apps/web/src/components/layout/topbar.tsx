import { PanelRight, Search } from "lucide-react";

export function Topbar() {
  return (
    <header className="flex h-11 shrink-0 items-center justify-between border-b border-[#e5e5df] bg-background px-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span>Workspace</span>
        <span className="rounded-full border px-2 py-0.5 text-[11px] font-normal text-muted-foreground">
          Preview
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <button
          className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          type="button"
        >
          <Search className="size-4" />
        </button>
        <button
          className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          type="button"
        >
          <PanelRight className="size-4" />
        </button>
      </div>
    </header>
  );
}
