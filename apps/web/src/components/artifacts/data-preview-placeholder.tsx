export function DataPreviewPlaceholder() {
  const rows = ["North", "South", "East", "West"];

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold">Data table preview</h2>
      <div className="mt-3 overflow-hidden rounded-md border">
        <div className="grid grid-cols-3 bg-[#f7f7f5] text-xs font-medium">
          <span className="p-2">Region</span>
          <span className="p-2">Revenue</span>
          <span className="p-2">Growth</span>
        </div>
        {rows.map((row, index) => (
          <div className="grid grid-cols-3 text-xs" key={row}>
            <span className="border-t p-2">{row}</span>
            <span className="border-t p-2">{(index + 3) * 120}k</span>
            <span className="border-t p-2 text-emerald-600">
              +{index + 8}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

