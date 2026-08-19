/**
 * File purpose: Renders and coordinates the ppt viewer user-interface feature.
 * Main declarations: PptViewer handles ppt viewer.
 */

"use client";

import { useState } from "react";

interface PptSlide {
  bullets?: string[];
  eyebrow?: string;
  subtitle?: string;
  title: string;
}

interface PptViewerProps {
  slides: PptSlide[];
  title: string;
}

export function PptViewer({ slides, title }: PptViewerProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selectedSlide = slides[selectedIndex] ?? slides[0];

  if (!selectedSlide) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">{title}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Slide {selectedIndex + 1} of {slides.length}
            </p>
          </div>
          <span className="rounded-full border px-2 py-1 text-xs text-muted-foreground">
            PPT preview
          </span>
        </div>

        <div className="aspect-video overflow-hidden rounded-lg border bg-[#f8f7ef] p-8 shadow-inner">
          <div className="flex h-full flex-col justify-between">
            <div>
              {selectedSlide.eyebrow ? (
                <div className="mb-4 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  {selectedSlide.eyebrow}
                </div>
              ) : null}
              <h3 className="max-w-[80%] text-2xl font-semibold leading-tight">
                {selectedSlide.title}
              </h3>
              {selectedSlide.subtitle ? (
                <p className="mt-3 max-w-[78%] text-sm leading-6 text-muted-foreground">
                  {selectedSlide.subtitle}
                </p>
              ) : null}
            </div>
            {selectedSlide.bullets?.length ? (
              <div className="grid gap-2">
                {selectedSlide.bullets.map((bullet) => (
                  <div
                    className="rounded-md border bg-white/80 px-3 py-2 text-xs"
                    key={bullet}
                  >
                    {bullet}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {slides.map((slide, index) => (
          <button
            className={`rounded-lg border bg-white p-2 text-left shadow-sm hover:bg-[#fafafa] ${
              index === selectedIndex ? "ring-2 ring-[#242424]" : ""
            }`}
            key={`${slide.title}-${index}`}
            onClick={() => setSelectedIndex(index)}
            type="button"
          >
            <div className="aspect-video rounded-md border bg-[#f8f7ef] p-3">
              <div className="h-2 w-1/2 rounded bg-[#242424]" />
              <div className="mt-3 h-1.5 w-4/5 rounded bg-muted" />
              <div className="mt-1.5 h-1.5 w-2/3 rounded bg-muted" />
            </div>
            <div className="mt-2 truncate text-xs font-medium">
              {index + 1}. {slide.title}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

