import { Paperclip } from "lucide-react";

export function FileUploadButton() {
  return (
    <button
      className="flex h-8 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
      type="button"
    >
      <Paperclip className="size-3.5" />
      Upload
    </button>
  );
}
