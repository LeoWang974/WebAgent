/**
 * File purpose: Renders and coordinates the data table viewer user-interface feature.
 * Main declarations: csvEscape handles csv escape; downloadCsv handles download csv;
 * DataTableViewer handles data table viewer.
 */

"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Search } from "lucide-react";

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

const PAGE_SIZE = 25;

function csvEscape(value: string) {
  return `"${value.replace(/"/g, '""')}"`;
}

function downloadCsv(title: string, columns: string[], rows: string[][]) {
  const csv = [columns, ...rows].map((row) => row.map(csvEscape).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${title.replace(/[\\/:*?"<>|]+/g, "-").slice(0, 80) || "table"}.csv`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function DataTableViewer({
  columns,
  rows,
  summary,
  title,
}: DataTableViewerProps) {
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const filteredRows = useMemo(() => {
    if (!normalizedQuery) {
      return rows;
    }
    return rows.filter((row) =>
      row.some((cell) => String(cell).toLowerCase().includes(normalizedQuery)),
    );
  }, [normalizedQuery, rows]);
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visibleRows = filteredRows.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">{title}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {filteredRows.length} / {rows.length} rows · {columns.length} columns
            </p>
          </div>
          <button
            className="flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            onClick={() => downloadCsv(title, columns, filteredRows)}
            type="button"
          >
            <Download className="size-3.5" />
            CSV
          </button>
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

        <label className="mb-3 flex h-9 items-center gap-2 rounded-md border bg-[#fbfbfa] px-2 text-sm">
          <Search className="size-4 text-muted-foreground" />
          <input
            className="min-w-0 flex-1 bg-transparent outline-none"
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
            placeholder="搜索表格内容"
            value={query}
          />
        </label>

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
              {visibleRows.map((row, rowIndex) => (
                <tr className="odd:bg-white even:bg-[#fbfbfa]" key={`${safePage}-${rowIndex}`}>
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
              {!visibleRows.length ? (
                <tr>
                  <td
                    className="px-3 py-8 text-center text-muted-foreground"
                    colSpan={columns.length}
                  >
                    没有匹配的数据。
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
          <span>
            Page {safePage + 1} / {pageCount}
          </span>
          <div className="flex items-center gap-1.5">
            <button
              className="flex size-8 items-center justify-center rounded-md border hover:bg-muted disabled:opacity-40"
              disabled={safePage === 0}
              onClick={() => setPage((value) => Math.max(0, value - 1))}
              type="button"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              className="flex size-8 items-center justify-center rounded-md border hover:bg-muted disabled:opacity-40"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
              type="button"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
