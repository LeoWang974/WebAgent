/**
 * File purpose: Renders and coordinates the session item user-interface feature.
 * Main declarations: SessionItem handles session item.
 */

"use client";

import { Check, Pencil, Pin, PinOff, Trash2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import type { FormEvent, MouseEvent } from "react";
import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { getStatusDotClass, getStatusLabelKey } from "@/lib/status";
import type { SessionStatus } from "@/types";
import type { ConversationFolder } from "@/types/session";

interface SessionItemProps {
  active?: boolean;
  folderId?: string;
  folders?: ConversationFolder[];
  href?: string;
  onClick?: () => void;
  onDelete?: () => void;
  onMoveToFolder?: (folderId?: string) => Promise<void> | void;
  onRename?: (title: string) => Promise<void> | void;
  onTogglePinned?: () => void;
  pinned?: boolean;
  status?: SessionStatus;
  switching?: boolean;
  title: string;
  updatedLabel?: string;
}

export function SessionItem({
  active = false,
  folderId,
  folders = [],
  href,
  onClick,
  onDelete,
  onMoveToFolder,
  onRename,
  onTogglePinned,
  pinned = false,
  status = "active",
  switching = false,
  title,
  updatedLabel,
}: SessionItemProps) {
  const { t } = useI18n();
  const router = useRouter();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(title);
  const [savingTitle, setSavingTitle] = useState(false);
  const className = `group flex w-full items-start gap-1 rounded-md hover:bg-[#e9e9e2] ${
    active ? "bg-white shadow-sm ring-1 ring-[#deded8]" : ""
  }`;

  async function saveTitle(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const nextTitle = draftTitle.trim();
    if (!nextTitle || nextTitle === title) {
      setDraftTitle(title);
      setEditing(false);
      return;
    }

    setSavingTitle(true);
    await onRename?.(nextTitle);
    setSavingTitle(false);
    setEditing(false);
  }

  const content = (
    <span className="min-w-0 flex-1">
      <span className="flex min-w-0 items-center justify-between gap-2">
        <span className="truncate text-[13px] leading-5">{title}</span>
        {updatedLabel ? (
          <span className="shrink-0 text-[10px] text-muted-foreground">
            {updatedLabel}
          </span>
        ) : null}
      </span>
      <span className="mt-0.5 flex items-center gap-1.5 text-[11px] capitalize text-muted-foreground">
        <span
          className={`size-1.5 rounded-full ${
            switching ? "bg-sky-500" : getStatusDotClass(status)
          }`}
        />
        {switching ? t("opening") : t(getStatusLabelKey(status))}
      </span>
    </span>
  );

  return (
    <div className={className}>
      {editing ? (
        <form
          className="min-w-0 flex-1 px-2 py-1.5"
          onSubmit={(event) => {
            void saveTitle(event);
          }}
        >
          <input
            autoFocus
            className="h-7 w-full rounded-md border border-[#d8d6cf] bg-white px-2 text-[13px] outline-none focus:border-[#242424]"
            disabled={savingTitle}
            onBlur={() => {
              void saveTitle();
            }}
            onChange={(event) => setDraftTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                setDraftTitle(title);
                setEditing(false);
              }
            }}
            value={draftTitle}
          />
        </form>
      ) : (
        <button
          className="min-w-0 flex-1 px-2 py-1.5 text-left"
          onClick={(event: MouseEvent<HTMLButtonElement>) => {
            event.preventDefault();
            onClick?.();
            if (href && window.location.pathname !== href) {
              router.push(href);
            }
          }}
          type="button"
        >
          {content}
        </button>
      )}
      {!confirmingDelete ? (
        <div className="mr-1 mt-1 flex shrink-0 items-center gap-1">
          <button
            aria-label="重命名会话"
            className={`flex size-6 items-center justify-center rounded-md text-muted-foreground opacity-0 hover:bg-white hover:text-foreground group-hover:opacity-100 ${
              active || editing ? "opacity-100" : ""
            }`}
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              event.stopPropagation();
              setDraftTitle(title);
              setEditing(true);
            }}
            title="重命名会话"
            type="button"
          >
            <Pencil className="size-3.5" />
          </button>
          {folders.length > 0 ? (
            <select
              aria-label="移动到目录"
              className={`h-6 max-w-8 rounded-md border bg-white text-[11px] text-muted-foreground opacity-0 outline-none group-hover:max-w-[92px] group-hover:opacity-100 ${
                active || folderId ? "opacity-100" : ""
              }`}
              onChange={(event) => {
                event.preventDefault();
                event.stopPropagation();
                void onMoveToFolder?.(event.target.value || undefined);
              }}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              title="移动到目录"
              value={folderId ?? ""}
            >
              <option value="">散放</option>
              {folders.map((folder) => (
                <option key={folder.id} value={folder.id}>
                  {folder.name}
                </option>
              ))}
            </select>
          ) : null}
          <button
            aria-label={pinned ? t("unpinConversation") : t("pinConversation")}
            className={`flex size-6 items-center justify-center rounded-md text-muted-foreground opacity-0 hover:bg-white hover:text-foreground group-hover:opacity-100 ${
              active || pinned ? "opacity-100" : ""
            }`}
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              event.stopPropagation();
              onTogglePinned?.();
            }}
            title={pinned ? t("unpinConversation") : t("pinConversation")}
            type="button"
          >
            {pinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
          </button>
          <button
            aria-label={t("deleteConversation")}
            className={`flex size-6 items-center justify-center rounded-md text-muted-foreground opacity-0 hover:bg-white hover:text-foreground group-hover:opacity-100 ${
              active ? "opacity-100" : ""
            }`}
            onClick={(event: MouseEvent<HTMLButtonElement>) => {
              event.preventDefault();
              event.stopPropagation();
              setConfirmingDelete(true);
            }}
            title={t("deleteConversation")}
            type="button"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      ) : (
        <div className="mr-1 mt-1 flex shrink-0 items-center gap-1">
          <button
            aria-label={t("confirmDelete")}
            className="flex size-6 items-center justify-center rounded-md bg-red-50 text-red-600 hover:bg-red-100"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onDelete?.();
            }}
            title={t("confirmDelete")}
            type="button"
          >
            <Check className="size-3.5" />
          </button>
          <button
            aria-label={t("cancel")}
            className="flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-white hover:text-foreground"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setConfirmingDelete(false);
            }}
            title={t("cancel")}
            type="button"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
