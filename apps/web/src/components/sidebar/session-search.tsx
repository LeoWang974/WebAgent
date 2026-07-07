import { Search } from "lucide-react";

export function SessionSearch() {
  return (
    <div className="flex h-8 items-center gap-2 rounded-md border border-[#dfdfd8] bg-white/70 px-2">
      <Search className="size-3.5 text-muted-foreground" />
      <input
        className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
        placeholder="Search"
        type="search"
      />
    </div>
  );
}
