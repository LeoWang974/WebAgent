"use client";

import type { MouseEvent } from "react";
import { useI18n } from "@/lib/i18n";
import { Check, Trash2, X } from "lucide-react";
import { useState } from "react";

interface SessionItemProps {
  active?: boolean;
  href?: string;
  onClick?: () => void;
  onDelete?: () => void;
  status?: string;
  switching?: boolean;
  title: string;
}

export function SessionItem({
  active = false,
  href,
  onClick,
  onDelete,
  status = "active",
  switching = false,
  title,
}: SessionItemProps) {
  const { t } = useI18n();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const className = `group flex w-full items-start gap-1 rounded-md hover:bg-[#e9e9e2] ${
    active ? "bg-white shadow-sm ring-1 ring-[#deded8]" : ""
  }`;
  const content = (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[13px] leading-5">{title}</span>
      <span className="mt-0.5 flex items-center gap-1.5 text-[11px] capitalize text-muted-foreground">
        <span
          className={`size-1.5 rounded-full ${
            switching
              ? "bg-sky-500"
              : status === "running"
                ? "bg-amber-500"
                : "bg-emerald-500"
          }`}
        />
        {switching
          ? t("opening")
          : status === "completed"
            ? t("completed")
            : status}
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
        <button
          aria-label={t("deleteConversation")}
          className={`mr-1 mt-1 flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 hover:bg-white hover:text-foreground group-hover:opacity-100 ${
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
