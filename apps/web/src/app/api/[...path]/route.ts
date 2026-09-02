/**
 * File purpose: Proxies same-origin WebAgent API requests to the internal FastAPI service.
 * Main declarations: proxyRequest forwards request method, headers, body, and streaming response;
 * GET, POST, PUT, PATCH, DELETE, and HEAD expose the proxy for matching API routes.
 */

import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const fetchCache = "force-no-store";

const INTERNAL_API_BASE_URL = (
  process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8010"
).replace(/\/$/, "");

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxyRequest(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const targetUrl = `${INTERNAL_API_BASE_URL}/api/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");

  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : await request.arrayBuffer();
  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  });

  const responseHeaders = new Headers(response.headers);
  for (const header of [
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
  ]) {
    responseHeaders.delete(header);
  }
  responseHeaders.set("cache-control", "no-cache, no-transform");
  responseHeaders.set("x-accel-buffering", "no");

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const HEAD = proxyRequest;
