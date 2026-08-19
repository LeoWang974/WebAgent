/**
 * File purpose: Renders and coordinates the image viewer user-interface feature.
 * Main declarations: ImageViewer handles image viewer.
 */

"use client";

import { useEffect, useState } from "react";
import { Download, ExternalLink } from "lucide-react";
import { useI18n } from "@/lib/i18n";

interface PreviewImage {
  gradient?: string;
  id: string;
  prompt: string;
  url?: string;
}

interface ImageViewerProps {
  images: PreviewImage[];
  title: string;
}

export function ImageViewer({ images, title }: ImageViewerProps) {
  const { t } = useI18n();
  const [selectedId, setSelectedId] = useState(images[0]?.id);
  const selectedImage = images.find((image) => image.id === selectedId) ?? images[0];

  useEffect(() => {
    setSelectedId(images[0]?.id);
  }, [images]);

  if (!selectedImage) {
    return null;
  }

  async function downloadSelectedImage() {
    if (!selectedImage?.url) {
      return;
    }
    const response = await fetch(selectedImage.url);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${selectedImage.id || "image"}.png`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  const renderImage = (image: PreviewImage, className: string) => {
    if (image.url) {
      return (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          alt={image.prompt || title}
          className={`${className} bg-[#f7f7f5] object-contain`}
          loading="lazy"
          src={image.url}
        />
      );
    }

    return (
      <div
        className={className}
        style={{
          background: image.gradient ?? "#f7f7f5",
        }}
      />
    );
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="mb-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold">{title}</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("generatedImagePreview")} ·{" "}
                {t("imageCount").replace("{count}", String(images.length))}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <button
                className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
                disabled={!selectedImage.url}
                onClick={() => {
                  if (selectedImage.url) {
                    window.open(selectedImage.url, "_blank", "noopener,noreferrer");
                  }
                }}
                title={t("openOriginalImage")}
                type="button"
              >
                <ExternalLink className="size-4" />
              </button>
              <button
                className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-40"
                disabled={!selectedImage.url}
                onClick={() => void downloadSelectedImage()}
                title={t("downloadCurrentImage")}
                type="button"
              >
                <Download className="size-4" />
              </button>
            </div>
          </div>
        </div>
        <div className="flex max-h-[70vh] min-h-[260px] items-center justify-center overflow-auto rounded-xl border bg-[#f7f7f5] p-2 shadow-inner">
          {renderImage(
            selectedImage,
            "max-h-[calc(70vh-24px)] max-w-full rounded-lg",
          )}
        </div>
        <p className="mt-3 rounded-md border bg-[#f7f7f5] p-3 text-xs leading-5 text-muted-foreground">
          {selectedImage.prompt}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {images.map((image) => (
          <button
            className={`rounded-lg border bg-white p-2 shadow-sm hover:bg-[#fafafa] ${
              image.id === selectedImage.id ? "ring-2 ring-[#242424]" : ""
            }`}
            key={image.id}
            onClick={() => setSelectedId(image.id)}
            type="button"
          >
            <div className="flex aspect-square items-center justify-center overflow-hidden rounded-md border bg-[#f7f7f5] p-1">
              {renderImage(image, "max-h-full max-w-full rounded-sm")}
            </div>
            <div className="mt-2 line-clamp-2 text-left text-xs text-muted-foreground">
              {image.prompt}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
