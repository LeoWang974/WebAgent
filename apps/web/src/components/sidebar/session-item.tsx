"use client";

import type { MouseEvent } from "react";
import { useI18n } from "@/lib/i18n";
import { getStatusDotClass, getStatusLabelKey } from "@/lib/status";
import { Check, Pin, PinOff, Trash2, X } from "lucide-react";
import { useState } from "react";
import type { SessionStatus } from "@/types";

interface SessionItemProps {
  active?: boolean;
  href?: string;
  onClick?: () => void;
  onDelete?: () => void;
  onTogglePinned?: () => void;
  pinned?: boolean;
  status?: SessionStatus;
  switching?: boolean;
  title: string;
  updatedLabel?: string;
}

export function SessionItem({
  active = false,
  href,
  onClick,
  onDelete,
  onTogglePinned,
  pinned = false,
  status = "active",
  switching = false,
  title,
  updatedLabel,
}: SessionItemProps) {
  const { t } = useI18n();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const className = `group flex w-full items-start gap-1 rounded-md hover:bg-[#e9e9e2] ${
    active ? "bg-white shadow-sm ring-1 ring-[#deded8]" : ""
  }`;
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
      <button
        className="min-w-0 flex-1 px-2 py-1.5 text-left"
        onClick={(event: MouseEvent<HTMLButtonElement>) => {
          event.preventDefault();
          onClick?.();
          if (href && window.location.pathname !== href) {
            window.location.assign(href);
          }
        }}
        type="button"
      >
        {content}
      </button>
      {!confirmingDelete ? (
        <div className="mr-1 mt-1 flex shrink-0 items-center gap-1">
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
