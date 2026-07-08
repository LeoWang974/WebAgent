interface DataSummaryItem {
  label: string;
  value: string;
}

interface DataTableViewerProps {
  columns: string[];
  rows: string[][];
  summary?: DataSummaryItem[];
  title: string;
}

export function DataTableViewer({
  columns,
  rows,
  summary,
  title,
}: DataTableViewerProps) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="mb-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {rows.length} rows / {columns.length} columns
          </p>
        </div>

        {summary?.length ? (
          <div className="mb-4 grid grid-cols-3 gap-2">
            {summary.map((item) => (
              <div className="rounded-md border bg-[#f7f7f5] p-3" key={item.label}>
                <div className="text-[11px] text-muted-foreground">
                  {item.label}
                </div>
                <div className="mt-1 text-sm font-semibold">{item.value}</div>
              </div>
            ))}
          </div>
        ) : null}

        <div className="overflow-x-auto rounded-md border">
          <table className="min-w-full border-collapse text-left text-xs">
            <thead className="bg-[#f7f7f5]">
              <tr>
                {columns.map((column) => (
                  <th className="border-b px-3 py-2 font-semibold" key={column}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr className="odd:bg-white even:bg-[#fbfbfa]" key={row.join("-")}>
                  {columns.map((column, columnIndex) => (
                    <td
                      className="border-b px-3 py-2 text-muted-foreground"
                      key={`${rowIndex}-${column}`}
                    >
                      {row[columnIndex]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

