"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { FileUploadButton } from "./file-upload-button";
import { ModelSelector } from "./model-selector";
import { SkillSelector } from "./skill-selector";
import type { SkillKey } from "@/types";
import { useChatStore, useUiStore } from "@/stores";
import { ArrowUp, Sparkles, Square } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function ChatComposer() {
  const { t } = useI18n();
  const [content, setContent] = useState("");
  const [skillKey, setSkillKey] = useState<SkillKey | undefined>();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeAgentRunId = useChatStore((state) => state.activeAgentRunId);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const stopActiveRun = useChatStore((state) => state.stopActiveRun);
  const sendShortcut = useUiStore((state) => state.sendShortcut);
  const running = Boolean(activeAgentRunId);

  useEffect(() => {
    const textarea = textareaRef.current;

    if (!textarea) {
      return;
    }

    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [content]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!content.trim() || running) {
      return;
    }

    sendMessage(content, skillKey);
    setContent("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    const modifierPressed = event.metaKey || event.ctrlKey;
    const shouldSubmit =
      sendShortcut === "enter"
        ? event.key === "Enter" && !event.shiftKey
        : event.key === "Enter" && modifierPressed;

    if (shouldSubmit) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form
      className="border-t border-[#ededeb] bg-background px-5 py-4"
      onSubmit={handleSubmit}
    >
      <div className="mx-auto max-w-3xl rounded-2xl border bg-white p-2 shadow-sm">
        <textarea
          className="max-h-[180px] min-h-14 w-full resize-none overflow-y-auto bg-transparent px-3 py-2 text-sm leading-6 outline-none placeholder:text-muted-foreground"
          onChange={(event) => setContent(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("composerPlaceholder")}
          ref={textareaRef}
          rows={1}
          value={content}
        />
        <div className="flex items-center justify-between gap-2 border-t px-1.5 pt-2">
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="hidden items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground sm:flex">
              <Sparkles className="size-3.5" />
              {t("autoRoute")}
            </span>
            <FileUploadButton />
            <SkillSelector value={skillKey} onChange={setSkillKey} />
            <ModelSelector />
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {running ? (
              <button
                aria-label={t("stop")}
                className="flex size-8 items-center justify-center rounded-lg border border-[#d8d8d2] bg-white text-muted-foreground hover:bg-[#f1f1ed] hover:text-foreground"
                onClick={stopActiveRun}
                title={t("stop")}
                type="button"
              >
                <Square className="size-3.5" />
              </button>
            ) : null}
            <button
              aria-label={t("send")}
              className="flex size-8 items-center justify-center rounded-lg bg-[#242424] text-white hover:bg-[#111] disabled:cursor-not-allowed disabled:opacity-40"
              disabled={!content.trim() || running}
              type="submit"
            >
              <ArrowUp className="size-4" />
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}
