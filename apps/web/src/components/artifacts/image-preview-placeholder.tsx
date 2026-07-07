export function ImagePreviewPlaceholder() {
  return (
    <div className="grid grid-cols-2 gap-3">
      {[1, 2, 3, 4].map((image) => (
        <div
          className="aspect-square rounded-lg border bg-white p-2 shadow-sm"
          key={image}
        >
          <div className="size-full rounded-md bg-[#e8e8e1]" />
        </div>
      ))}
    </div>
  );
}

