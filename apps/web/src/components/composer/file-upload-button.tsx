import { Paperclip } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function FileUploadButton() {
  const { t } = useI18n();

  return (
    <button
      className="flex h-8 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
      type="button"
    >
      <Paperclip className="size-3.5" />
      {t("upload")}
    </button>
  );
}
