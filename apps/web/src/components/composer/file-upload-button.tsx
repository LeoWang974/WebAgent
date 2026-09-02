/**
 * File purpose: Renders and coordinates the file upload button user-interface feature.
 * Main declarations: FileUploadButton handles file upload button.
 */

"use client";

import { ChangeEvent, useRef, useState } from "react";
import { Paperclip } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface FileUploadButtonProps {
  disabled?: boolean;
  onUpload: (file: File) => Promise<void>;
}

export function FileUploadButton({ disabled = false, onUpload }: FileUploadButtonProps) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    setError(undefined);
    setUploading(true);
    try {
      await onUpload(file);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <input
        accept=".csv,.json,.pdf,.ppt,.pptx,.xls,.xlsx,.gif,.jpeg,.jpg,.png,.webp,.htm,.html,.md,.markdown,.txt"
        className="hidden"
        onChange={handleChange}
        ref={inputRef}
        type="file"
      />
      <button
        aria-busy={uploading}
        className="flex h-8 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
        title={error}
        type="button"
      >
        <Paperclip className="size-3.5" />
        {uploading ? "…" : error ? "!" : t("upload")}
      </button>
    </>
  );
}
