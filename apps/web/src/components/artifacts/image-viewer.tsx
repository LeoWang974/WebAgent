"use client";

import { useEffect, useState } from "react";
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

  const renderImage = (image: PreviewImage, className: string) => {
    if (image.url) {
      return (
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
          <h2 className="text-sm font-semibold">{title}</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("generatedImagePreview")}
          </p>
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

      <div className="grid grid-cols-2 gap-3">
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
