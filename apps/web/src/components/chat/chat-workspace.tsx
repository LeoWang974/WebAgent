/**
 * File purpose: Renders and coordinates the chat workspace user-interface feature.
 * Main declarations: ChatWorkspace handles chat workspace.
 */

"use client";

import { ArtifactDrawer, ArtifactFullscreen, ArtifactPanel } from "../artifacts";
import { ChatComposer } from "../composer";
import { AgentStatus } from "./agent-status";
import { ChatHeader } from "./chat-header";
import { MessageList } from "./message-list";
import { RouteSessionSync } from "./route-session-sync";
import { WorkspaceState } from "./workspace-state";
import { GripVertical } from "lucide-react";
import { useEffect, useState } from "react";
import { useUiStore } from "@/stores";
import { useI18n } from "@/lib/i18n";

interface ChatWorkspaceProps {
  sessionId?: string;
}

export function ChatWorkspace({ sessionId }: ChatWorkspaceProps) {
  const { t } = useI18n();
  const artifactPanelOpen = useUiStore((state) => state.artifactPanelOpen);
  const artifactPanelWidth = useUiStore((state) => state.artifactPanelWidth);
  const setArtifactPanelWidth = useUiStore(
    (state) => state.setArtifactPanelWidth,
  );
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    return () => {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, []);

  function startResize(pointerId: number, target: HTMLElement) {
    setDragging(true);
    target.setPointerCapture(pointerId);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  function stopResize(pointerId: number, target: HTMLElement) {
    setDragging(false);
    if (target.hasPointerCapture(pointerId)) {
      target.releasePointerCapture(pointerId);
    }
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }

  return (
    <div className="relative flex h-full min-h-0">
      <RouteSessionSync sessionId={sessionId} />
      <WorkspaceState />
      <section className="flex min-w-0 flex-1 flex-col">
        <ChatHeader />
        <div className="min-h-0 flex-1 overflow-hidden">
          <MessageList />
        </div>
        <AgentStatus />
        <ChatComposer />
      </section>
      {artifactPanelOpen ? (
        <button
          aria-label={t("resizeArtifactPanel")}
          className={`hidden w-2 shrink-0 cursor-col-resize items-center justify-center border-l border-[#deded8] bg-[#f7f7f5] text-muted-foreground hover:bg-[#ecece6] xl:flex ${
            dragging ? "bg-[#ecece6]" : ""
          }`}
          onPointerCancel={(event) =>
            stopResize(event.pointerId, event.currentTarget)
          }
          onPointerDown={(event) =>
            startResize(event.pointerId, event.currentTarget)
          }
          onLostPointerCapture={() => {
            setDragging(false);
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
          }}
          onPointerMove={(event) => {
            if (!dragging) {
              return;
            }

            setArtifactPanelWidth(window.innerWidth - event.clientX);
          }}
          onPointerUp={(event) => stopResize(event.pointerId, event.currentTarget)}
          title={t("resizeArtifactPanel")}
          type="button"
        >
          <GripVertical className="size-3" />
        </button>
      ) : null}
      <ArtifactPanel dragging={dragging} width={artifactPanelWidth} />
      <ArtifactDrawer />
      <ArtifactFullscreen />
    </div>
  );
}
