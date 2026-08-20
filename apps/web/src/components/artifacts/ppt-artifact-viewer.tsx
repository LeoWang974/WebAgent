/**
 * File purpose: Renders and coordinates the ppt artifact viewer user-interface feature.
 * Main declarations: slideTitle handles slide title; SlideFrame handles slide frame;
 * PptArtifactViewer handles ppt artifact viewer.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Loader2, Maximize, Minus, Plus, Presentation } from "lucide-react";
import { downloadArtifact } from "@/lib/artifact-actions";
import { webAgentApi } from "@/services";
import type { Artifact, SlidePreview } from "@/types";
import { FileArtifactViewer } from "./file-artifact-viewer";

interface PptArtifactViewerProps {
  artifact: Artifact;
}

interface SlideFrameProps {
  className?: string;
  content: string;
  interactive?: boolean;
  zoom?: number;
  title: string;
}

const SLIDE_WIDTH = 1280;
const SLIDE_HEIGHT = 720;

function slideTitle(slide: SlidePreview) {
  return slide.title || `Slide ${slide.index}`;
}

function SlideFrame({
  className = "",
  content,
  interactive = false,
  title,
  zoom,
}: SlideFrameProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) {
      return;
    }

    const updateScale = () => {
      const { width, height } = frame.getBoundingClientRect();
      if (!width || !height) {
        return;
      }
      setScale(Math.min(width / SLIDE_WIDTH, height / SLIDE_HEIGHT));
    };

    updateScale();
    const observer = new ResizeObserver(updateScale);
    observer.observe(frame);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      className={`relative aspect-video overflow-hidden rounded-md border bg-white ${className}`}
      ref={frameRef}
    >
      <iframe
        className={
          interactive
            ? "absolute left-0 top-0 bg-white"
            : "pointer-events-none absolute left-0 top-0 bg-white"
        }
        sandbox=""
        srcDoc={content}
        style={{
          height: SLIDE_HEIGHT,
          transform: `scale(${zoom ?? scale})`,
          transformOrigin: "top left",
          width: SLIDE_WIDTH,
        }}
        tabIndex={interactive ? undefined : -1}
        title={title}
      />
    </div>
  );
}

export function PptArtifactViewer({ artifact }: PptArtifactViewerProps) {
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [previewSource, setPreviewSource] = useState<string>();
  const [retryKey, setRetryKey] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [slides, setSlides] = useState<SlidePreview[]>([]);
  const [zoom, setZoom] = useState<number | undefined>();

  useEffect(() => {
    let cancelled = false;

    async function loadSlides() {
      setError(undefined);
      setLoading(true);
      let lastError: unknown;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const result = await webAgentApi.getArtifactSlides(artifact.id);
          if (!cancelled) {
            setSlides(result.slides);
            setPreviewSource(result.source);
            setSelectedIndex(0);
          }
          lastError = undefined;
          break;
        } catch (loadError) {
          lastError = loadError;
          if (attempt === 0) {
            await new Promise((resolve) => window.setTimeout(resolve, 350));
          }
        }
      }
      if (!cancelled && lastError) {
        setError(lastError instanceof Error ? lastError.message : "Failed to render slides.");
      }
      if (!cancelled) {
        setLoading(false);
      }
    }

    void loadSlides();
    return () => {
      cancelled = true;
    };
  }, [artifact.id, retryKey]);

  const selectedSlide = slides[selectedIndex];
  const canPreview = slides.length > 0 && selectedSlide?.content;
  const slideCounter = useMemo(() => {
    if (!slides.length) {
      return "0 / 0";
    }
    return `${selectedIndex + 1} / ${slides.length}`;
  }, [selectedIndex, slides.length]);
  const zoomLabel = zoom ? `${Math.round(zoom * 100)}%` : "适配";

  if (loading) {
    return (
      <div className="flex min-h-[320px] items-center justify-center rounded-lg border bg-white">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          正在渲染幻灯片预览...
        </div>
      </div>
    );
  }

  if (!canPreview) {
    return (
      <FileArtifactViewer
        actionLabel="重新渲染"
        artifact={artifact}
        description={
          error
            ? `幻灯片渲染失败：${error}`
            : "PPTX 文件已就绪，但暂时无法生成浏览器预览。"
        }
        onAction={() => setRetryKey((value) => value + 1)}
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg border bg-white shadow-sm">
        <div className="flex items-center justify-between gap-3 border-b px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-md border bg-[#f7f7f5]">
              <Presentation className="size-4" />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold">{artifact.title}</h2>
              <p className="text-xs text-muted-foreground">Slide {slideCounter}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => setZoom((value) => Math.max(0.5, (value ?? 1) - 0.1))}
              title="缩小"
              type="button"
            >
              <Minus className="size-4" />
            </button>
            <button
              className="h-8 min-w-12 rounded-md border px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => setZoom(undefined)}
              title="适配宽高"
              type="button"
            >
              {zoomLabel}
            </button>
            <button
              className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => setZoom((value) => Math.min(1.5, (value ?? 1) + 0.1))}
              title="放大"
              type="button"
            >
              <Plus className="size-4" />
            </button>
            <button
              className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => setZoom(undefined)}
              title="适配宽高"
              type="button"
            >
              <Maximize className="size-4" />
            </button>
            <button
              className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
              disabled={selectedIndex === 0}
              onClick={() => setSelectedIndex((value) => Math.max(0, value - 1))}
              type="button"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
              disabled={selectedIndex >= slides.length - 1}
              onClick={() => setSelectedIndex((value) => Math.min(slides.length - 1, value + 1))}
              type="button"
            >
              <ChevronRight className="size-4" />
            </button>
            <button
              className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => void downloadArtifact(artifact)}
              title="下载 PPTX"
              type="button"
            >
              <Download className="size-4" />
            </button>
          </div>
        </div>
        <div className="border-b bg-[#fbfbfa] px-3 py-2 text-xs text-muted-foreground">
          {previewSource === "pptx_rendered"
            ? "预览由服务端从 PPTX 渲染；下载按钮获取 PPTX 原文件。"
            : "预览来自配套 HTML 或图片页面；下载按钮获取 PPTX 原文件。"}
        </div>
        <div className="bg-[#eeeeea] p-3">
          <SlideFrame
            className={zoom ? "overflow-auto shadow-inner" : "shadow-inner"}
            content={selectedSlide.content ?? ""}
            interactive
            title={slideTitle(selectedSlide)}
            zoom={zoom}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
        {slides.map((slide, index) => (
          <button
            className={`rounded-lg border bg-white p-2 text-left shadow-sm hover:bg-[#fafafa] ${
              index === selectedIndex ? "ring-2 ring-[#242424]" : ""
            }`}
            key={slide.id}
            onClick={() => setSelectedIndex(index)}
            type="button"
          >
            <div className="rounded-md bg-[#f7f7f5]">
              {slide.content ? (
                <SlideFrame
                  content={slide.content}
                  title={`Thumbnail ${slide.index}`}
                />
              ) : null}
            </div>
            <div className="mt-2 truncate text-xs font-medium">
              {slide.index}. {slideTitle(slide)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
