export function PptPreviewPlaceholder() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((slide) => (
        <div className="rounded-lg border bg-white p-3 shadow-sm" key={slide}>
          <div className="mb-2 text-xs font-medium text-muted-foreground">
            Slide {slide}
          </div>
          <div className="aspect-video rounded-md border bg-[#f7f7f5] p-5">
            <div className="h-4 w-2/3 rounded bg-[#242424]" />
            <div className="mt-4 h-2 w-full rounded bg-muted" />
            <div className="mt-2 h-2 w-4/5 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

