/**
 * useTabs — tab CRUD operations via backend API.
 */

import { useState, useCallback } from "react";
import type { ApiClient } from "../api/client";
import type { Tab } from "../types/index";

export interface UseTabsResult {
  /** Currently active tab (null before any tab is selected/opened) */
  activeTab: Tab | null;
  /** All open tabs (for TabList view) */
  openTabs: Tab[];
  /** Loading state for tab operations */
  loading: boolean;
  /** Error message from last operation */
  error: string | null;
  /** Open or switch to a tab for a given table */
  openTab: (tableId: number, terminalId: string) => Promise<void>;
  /** Set the active tab from an existing open tab */
  selectTab: (tab: Tab) => void;
  /** Add item to active tab */
  addItem: (
    productId: number,
    qty?: number,
    overridePrice?: string,
  ) => Promise<void>;
  /** Remove item from active tab */
  removeItem: (itemId: number) => Promise<void>;
  /** Update item quantity on active tab */
  updateQty: (itemId: number, qty: number) => Promise<void>;
  /** Send tab to POS cart (records transaction in backend) */
  sendToCart: () => Promise<{ transaction_id: number }>;
  /** Close tab */
  closeTab: () => Promise<void>;
  /** Refresh the open tabs list */
  refreshOpenTabs: () => Promise<void>;
  /** Clear error */
  clearError: () => void;
}

export function useTabs(api: ApiClient): UseTabsResult {
  const [activeTab, setActiveTab] = useState<Tab | null>(null);
  const [openTabs, setOpenTabs] = useState<Tab[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const withError = useCallback(<T,>(fn: () => Promise<T>): Promise<T> => {
    setError(null);
    setLoading(true);
    return fn()
      .then((result) => {
        setLoading(false);
        return result;
      })
      .catch((err: Error) => {
        setLoading(false);
        setError(err.message);
        throw err;
      });
  }, []);

  const openTab = useCallback(
    async (tableId: number, terminalId: string) => {
      const tab = await withError(() => api.openTab(tableId, terminalId));
      setActiveTab(tab);
      // Refresh open tabs list
      try {
        const open = await api.getOpenTabs();
        setOpenTabs(open);
      } catch {
        // Non-critical
      }
    },
    [api, withError],
  );

  const selectTab = useCallback((tab: Tab) => {
    setActiveTab(tab);
  }, []);

  const addItem = useCallback(
    async (productId: number, qty?: number, overridePrice?: string) => {
      if (!activeTab) return;
      const updated = await withError(() =>
        api.addTabItem(activeTab.id, productId, qty, overridePrice),
      );
      setActiveTab(updated);
    },
    [activeTab, api, withError],
  );

  const removeItem = useCallback(
    async (itemId: number) => {
      if (!activeTab) return;
      await withError(() => api.removeTabItem(activeTab.id, itemId));
      // Refresh the tab
      const updated = await withError(() => api.getTab(activeTab.table_id));
      setActiveTab(updated);
    },
    [activeTab, api, withError],
  );

  const updateQty = useCallback(
    async (itemId: number, qty: number) => {
      if (!activeTab) return;
      if (qty <= 0) {
        await removeItem(itemId);
        return;
      }
      const updated = await withError(() =>
        api.updateTabItemQty(activeTab.id, itemId, qty),
      );
      setActiveTab(updated);
    },
    [activeTab, api, withError, removeItem],
  );

  const sendToCart = useCallback(async () => {
    if (!activeTab) throw new Error("No active tab");
    return await withError(() => api.sendToCart(activeTab.id));
  }, [activeTab, api, withError]);

  const closeTab = useCallback(async () => {
    if (!activeTab) return;
    await withError(() => api.closeTab(activeTab.id));
    setActiveTab(null);
    // Refresh open tabs
    try {
      const open = await api.getOpenTabs();
      setOpenTabs(open);
    } catch {
      // Non-critical
    }
  }, [activeTab, api, withError]);

  const refreshOpenTabs = useCallback(async () => {
    try {
      const open = await api.getOpenTabs();
      setOpenTabs(open);
    } catch {
      // Non-critical
    }
  }, [api]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    activeTab,
    openTabs,
    loading,
    error,
    openTab,
    selectTab,
    addItem,
    removeItem,
    updateQty,
    sendToCart,
    closeTab,
    refreshOpenTabs,
    clearError,
  };
}
