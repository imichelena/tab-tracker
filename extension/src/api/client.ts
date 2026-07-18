/**
 * Typed API client for the Tab Tracker backend.
 *
 * Configured via extension settings (api_url + api_key).
 * Respects the POS sandbox constraint — uses plain fetch.
 */

import type { Product, Category, Table, Tab, ApiError } from "../types/index";

export type { ApiError };

const DEFAULT_RETRY_DELAY_MS = 500;
const MAX_RETRIES = 3;

/**
 * Backend API error with HTTP status code.
 */
export class BackendApiError extends Error {
  public status: number;
  public details?: string;

  constructor(status: number, message: string, details?: string) {
    super(message);
    this.name = "BackendApiError";
    this.status = status;
    this.details = details;
  }
}

/**
 * Network/connectivity error (backend unreachable).
 */
export class NetworkError extends Error {
  constructor(message = "Backend is unreachable. Check your network connection.") {
    super(message);
    this.name = "NetworkError";
  }
}

/**
 * Escape hatch for sending the request via a Shopify draft order instead.
 */
export class DraftOrderFallback extends Error {
  public tabId: number;

  constructor(tabId: number, message = "Send-to-cart failed after retries. Use draft order fallback.") {
    super(message);
    this.name = "DraftOrderFallback";
    this.tabId = tabId;
  }
}

interface ClientConfig {
  baseUrl: string;
  apiKey: string;
  shopLocationId?: string;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Create a configured API client.
 *
 * In a real Shopify POS extension, baseUrl and apiKey would come from
 * extension settings or app metafields. For development, they can be
 * overridden via env vars or a config object.
 */
export function createApiClient(config: ClientConfig) {
  const { baseUrl, apiKey, shopLocationId } = config;

  async function request<T>(
    path: string,
    options?: RequestInit,
    retries = MAX_RETRIES,
  ): Promise<T> {
    const url = `${baseUrl}${path}`;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    };
    if (shopLocationId) {
      headers["X-Shop-Location"] = shopLocationId;
    }

    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const res = await fetch(url, {
          ...options,
          headers: {
            ...headers,
            ...(options?.headers as Record<string, string> | undefined),
          },
        });

        if (res.status === 401) {
          const text = await res.text();
          throw new BackendApiError(
            401,
            "Unauthorized — check API key",
            text,
          );
        }

        if (res.status >= 500) {
          const text = await res.text();
          throw new BackendApiError(
            res.status,
            `Backend error (${res.status})`,
            text,
          );
        }

        if (!res.ok) {
          const text = await res.text();
          throw new BackendApiError(res.status, text || `HTTP ${res.status}`);
        }

        // 204 No Content (DELETE, etc.)
        if (res.status === 204 || res.headers.get("content-length") === "0") {
          return undefined as unknown as T;
        }

        return (await res.json()) as T;
      } catch (err) {
        if (err instanceof BackendApiError) {
          // Don't retry client errors (4xx) except 429 (rate limit)
          if (err.status < 500 && err.status !== 429) {
            throw err;
          }
        }

        if (err instanceof TypeError && err.message.includes("fetch")) {
          lastError = new NetworkError();
        } else {
          lastError = err instanceof Error ? err : new Error(String(err));
        }

        if (attempt < retries) {
          const delay = DEFAULT_RETRY_DELAY_MS * Math.pow(2, attempt);
          await sleep(delay);
        }
      }
    }

    throw lastError ?? new Error("Request failed after retries");
  }

  return {
    /** GET /api/v1/products */
    getProducts: (): Promise<Product[]> =>
      request<Product[]>("/api/v1/products"),

    /** GET /api/v1/categories */
    getCategories: (): Promise<Category[]> =>
      request<Category[]>("/api/v1/categories"),

    /** GET /api/v1/tables */
    getTables: (): Promise<Table[]> =>
      request<Table[]>("/api/v1/tables"),

    /** GET /api/v1/tabs?table_id=N — get open tab for a table */
    getTab: (tableId: number): Promise<Tab> =>
      request<Tab>(`/api/v1/tabs?table_id=${tableId}`),

    /** POST /api/v1/tabs — open a new tab */
    openTab: (tableId: number, terminalId: string): Promise<Tab> =>
      request<Tab>("/api/v1/tabs", {
        method: "POST",
        body: JSON.stringify({
          table_id: tableId,
          pos_terminal_id: terminalId,
        }),
      }),

    /** POST /api/v1/tabs/{tabId}/items — add item to tab */
    addTabItem: (
      tabId: number,
      productId: number,
      qty = 1,
      overridePrice?: string,
    ): Promise<Tab> =>
      request<Tab>(`/api/v1/tabs/${tabId}/items`, {
        method: "POST",
        body: JSON.stringify({
          product_id: productId,
          quantity: qty,
          override_price: overridePrice,
        }),
      }),

    /** DELETE /api/v1/tabs/{tabId}/items/{itemId} */
    removeTabItem: (tabId: number, itemId: number): Promise<void> =>
      request<void>(`/api/v1/tabs/${tabId}/items/${itemId}`, {
        method: "DELETE",
      }),

    /** PATCH /api/v1/tabs/{tabId}/items/{itemId} — update quantity */
    updateTabItemQty: (
      tabId: number,
      itemId: number,
      qty: number,
    ): Promise<Tab> =>
      request<Tab>(`/api/v1/tabs/${tabId}/items/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify({ quantity: qty }),
      }),

    /** POST /api/v1/tabs/{tabId}/send-to-cart */
    sendToCart: (
      tabId: number,
    ): Promise<{ transaction_id: number }> =>
      request<{ transaction_id: number }>(
        `/api/v1/tabs/${tabId}/send-to-cart`,
        { method: "POST" },
      ),

    /** GET /api/v1/tabs/open */
    getOpenTabs: (): Promise<Tab[]> =>
      request<Tab[]>("/api/v1/tabs/open"),

    /** POST /api/v1/tabs/{tabId}/close */
    closeTab: (tabId: number): Promise<void> =>
      request<void>(`/api/v1/tabs/${tabId}/close`, {
        method: "POST",
      }),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
