import { useState, useEffect, useMemo, type ReactElement } from "react";
import { createApiClient } from "./api/client";
import { sendItemsToCart } from "./hooks/useCartApi";
import type { CartApiHandle } from "./hooks/useCartApi";
import {
  Box,
  Button,
  Screen,
  ScrollView,
  SectionHeader,
  Stack,
  Text,
  reactExtension,
  useApi,
  Banner,
} from "@shopify/ui-extensions-react/point-of-sale";

/**
 * Tab Tracker modal — the full-screen interface for managing table tabs.
 *
 * Layout:
 * ┌─────────────────────────────────┐
 * │  Header: Tab Tracker    [Close] │
 * ├────────────────┬────────────────┤
 * │  Left Panel    │  Right Panel   │
 * │  (Category +   │  (Tab Bill)    │
 * │   Products)    │                │
 * ├────────────────┴────────────────┤
 * │  [Send to POS Cart] (sticky)    │
 * └─────────────────────────────────┘
 */

interface Product {
  id: number;
  name: string;
  price: string;
  category_id: number;
  category_name: string;
  shopify_variant_id: number | null;
  image_path: string | null;
  override_price: string | null;
}

interface Category {
  id: number;
  name: string;
  sort_order: number;
}

interface TableInfo {
  id: number;
  name: string;
}

interface TabItem {
  id: number;
  tab_id: number;
  product_id: number;
  product_name: string;
  shopify_variant_id: number | null;
  unit_price: string;
  override_price: string | null;
  quantity: number;
  line_total: string;
}

type TabStatus = "open" | "sent" | "closed";

interface Tab {
  id: number;
  table_id: number;
  table_name: string;
  status: TabStatus;
  items: TabItem[];
  total: string;
  notes: string | null;
  pos_cart_sent_at: string | null;
  created_at: string;
  updated_at: string;
}

type ViewState =
  | { type: "loading" }
  | { type: "tabList" }
  | { type: "tabDetail" }
  | { type: "error"; message: string }
  | { type: "sending" }
  | { type: "success" };

function TabTrackerModal(): ReactElement {
  const apiHook = useApi<"pos.home.modal.render">();

  // ── API Client (from extension settings with dev fallback) ──
  // Read settings from shopify.extension.toml [settings] block.
  // In production these MUST be configured by the merchant.
  const apiSettings = (apiHook as unknown as { settings?: Record<string, string> }).settings;
  const apiClient = useMemo(() => {
    const backendUrl = apiSettings?.backend_url;
    const apiKey = apiSettings?.api_key;

    if (backendUrl && apiKey) {
      return createApiClient({
        baseUrl: backendUrl,
        apiKey,
        shopLocationId: apiSettings?.default_terminal_id || undefined,
      });
    }

    // ════════════════════════════════════════════════════════════════
    // DEV FALLBACK — only for local development
    // ════════════════════════════════════════════════════════════════
    // In production, missing settings cause a hard crash so dev values
    // never leak into a deployed environment.  Vite replaces
    // import.meta.env.PROD with a literal `true` at build time, and
    // dead-code elimination removes this entire branch.
    // @ts-expect-error — import.meta.env is a Vite compile-time constant
    if (import.meta.env.PROD) {
      throw new Error(
        "[TabTracker] Missing required extension settings: backend_url and api_key. " +
        "Configure them in shopify.extension.toml [settings] block before deploying.",
      );
    }

    console.warn(
      "[TabTracker] Using dev fallback settings. " +
      "Configure backend_url and api_key in shopify.extension.toml [settings] for production.",
    );

    return createApiClient({
      baseUrl: "http://localhost:8095",
      apiKey: "test-key",
      shopLocationId: "dev-001",
    });
  }, [apiSettings]);

  const terminalId = apiSettings?.default_terminal_id || "dev-001";

  const [viewState, setViewState] = useState<ViewState>({ type: "loading" });
  const [activeCategory, setActiveCategory] = useState<number | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [activeTab, setActiveTab] = useState<Tab | null>(null);
  const [openTabs, setOpenTabs] = useState<Tab[]>([]);

  // Load on mount
  async function loadInitialData() {
    setViewState({ type: "loading" });
    try {
      const [prods, cats, tabs] = await Promise.all([
        apiClient.getProducts(),
        apiClient.getCategories(),
        apiClient.getTables(),
      ]);
      setProducts(prods);
      setCategories(cats);
      setTables(tabs);

      // Try to fetch open tabs
      try {
        const open = await apiClient.getOpenTabs();
        setOpenTabs(open);
      } catch {
        // No open tabs yet — that's fine
        setOpenTabs([]);
      }

      setViewState({ type: "tabList" });
    } catch (err) {
      setViewState({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to load data",
      });
    }
  }

  useEffect(() => {
    void loadInitialData();
  }, []);

  // ── Tab operations ──
  async function handleOpenTab(tableId: number) {
    try {
      const tab = await apiClient.openTab(tableId, terminalId);
      setActiveTab(tab);
      setViewState({ type: "tabDetail" });
    } catch (err) {
      setViewState({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to open tab",
      });
    }
  }

  async function handleSelectTab(tab: Tab) {
    setActiveTab(tab);
    setViewState({ type: "tabDetail" });
  }

  async function handleAddProduct(product: Product) {
    if (!activeTab) return;
    try {
      const overridePrice =
        product.override_price && product.override_price !== product.price
          ? product.override_price
          : undefined;
      const updated = await apiClient.addTabItem(
        activeTab.id,
        product.id,
        1,
        overridePrice,
      );
      setActiveTab(updated);
    } catch (err) {
      setViewState({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to add item",
      });
    }
  }

  async function handleRemoveItem(itemId: number) {
    if (!activeTab) return;
    try {
      await apiClient.removeTabItem(activeTab.id, itemId);
      // Refresh the tab
      const updated = await apiClient.getTab(activeTab.table_id);
      setActiveTab(updated);
    } catch (err) {
      setViewState({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to remove item",
      });
    }
  }

  async function handleUpdateQty(itemId: number, qty: number) {
    if (!activeTab) return;
    if (qty <= 0) {
      await handleRemoveItem(itemId);
      return;
    }
    try {
      const updated = await apiClient.updateTabItemQty(activeTab.id, itemId, qty);
      setActiveTab(updated);
    } catch (err) {
      setViewState({
        type: "error",
        message:
          err instanceof Error ? err.message : "Failed to update quantity",
      });
    }
  }

  async function handleSendToCart() {
    if (!activeTab || activeTab.items.length === 0) return;
    setViewState({ type: "sending" });

    try {
      // 1. Send items to POS Cart via Cart API (clearCart → addLineItem/addCustomSale)
      // Get Cart API handle from POS extension runtime context
      const cartApi = (apiHook as unknown as { cart?: CartApiHandle }).cart;
      if (!cartApi) {
        throw new Error("Cart API not available in this POS context");
      }

      const progress = await sendItemsToCart(cartApi, activeTab.items);

      if (progress.failed.length > 0 && progress.succeeded === 0) {
        // All items failed — do NOT call backend (no phantom transaction)
        setViewState({
          type: "error",
          message: `Failed to add items to cart. ${progress.failed[0]?.reason ?? "Unknown error"}`,
        });
        return;
      }

      // 2. Record transaction in backend (only if at least some items succeeded)
      if (progress.succeeded > 0) {
        await apiClient.sendToCart(activeTab.id);
      }

      setViewState({ type: "success" });

      // Auto-close after 2.5 seconds
      setTimeout(() => {
        void apiHook.action.presentModal();
      }, 2500);
    } catch (err) {
      setViewState({
        type: "error",
        message:
          err instanceof Error ? err.message : "Failed to send items to cart",
      });
    }
  }

  // ── Render: Loading ──
  if (viewState.type === "loading") {
    return (
      <Screen name="TabTracker" title="Tab Tracker" isLoading>
        <ScrollView>
          <Box padding="200" paddingBlock="400">
            <Stack direction="block" justifyContent="center" gap="300">
              <Text variant="body">Loading…</Text>
              <Text variant="captionRegular" color="TextSubdued">
                Fetching tables, products, and open tabs
              </Text>
            </Stack>
          </Box>
        </ScrollView>
      </Screen>
    );
  }

  // ── Render: Error ──
  if (viewState.type === "error") {
    return (
      <Screen name="TabTracker" title="Tab Tracker">
        <ScrollView>
          <Box padding="200">
            <Banner
              title="Error"
              variant="error"
              visible
              action="Retry"
              onPress={() => loadInitialData()}
            >
              {viewState.message}
            </Banner>
            <Box padding="200" />
            <Button
              title="Close"
              type="basic"
              onPress={() => {
                void apiHook.action.presentModal();
              }}
            />
          </Box>
        </ScrollView>
      </Screen>
    );
  }

  // ── Render: Tab List (initial view) ──
  if (viewState.type === "tabList") {
    const filteredProducts = activeCategory
      ? products.filter((p) => p.category_id === activeCategory)
      : products;

    return (
      <Screen name="TabTracker" title="Tab Tracker">
        <ScrollView>
          {/* ── Category Bar ── */}
          <Box padding="200" paddingBlock="100">
            <Stack direction="inline" gap="100">
              <Button
                title="All"
                type={activeCategory === null ? "primary" : "basic"}
                onPress={() => setActiveCategory(null)}
              />
              {categories.map((cat) => (
                <Button
                  key={cat.id}
                  title={cat.name}
                  type={activeCategory === cat.id ? "primary" : "basic"}
                  onPress={() =>
                    setActiveCategory(
                      activeCategory === cat.id ? null : cat.id,
                    )
                  }
                />
              ))}
            </Stack>
          </Box>

          {/* ── Product Grid ── */}
          <Box padding="200">
            <Stack direction="inline" gap="100" flexWrap="wrap">
              {filteredProducts.length === 0 && (
                <Text variant="body" color="TextSubdued">
                  No products found
                </Text>
              )}
              {filteredProducts.map((product) => (
                <Box key={product.id} inlineSize="300px" padding="100">
                  <Stack direction="block" gap="050">
                    <Text variant="body">{product.name}</Text>
                    {product.override_price &&
                    product.override_price !== product.price ? (
                      <Text variant="captionMedium" color="TextSuccess">
                        €{product.override_price}
                        <Text variant="captionRegular" color="TextSubdued">
                          {" "}(€{product.price})
                        </Text>
                      </Text>
                    ) : (
                      <Text variant="captionMedium">€{product.price}</Text>
                    )}
                    <Button
                      title="Add"
                      type="primary"
                      onPress={() => handleAddProduct(product)}
                    />
                  </Stack>
                </Box>
              ))}
            </Stack>
          </Box>
        </ScrollView>

        {/* ── Tab Bill Panel (right side / bottom) ── */}
        {activeTab && (
          <Box padding="200" paddingBlock="100">
            <SectionHeader
              title={`Tab: ${activeTab.table_name}`}
              action={{
                label: "Change Table",
                onPress: () => setViewState({ type: "tabList" }),
              }}
            />
            <ScrollView>
              {activeTab.items.length === 0 ? (
                <Text variant="body" color="TextSubdued">
                  No items yet — tap a product to add
                </Text>
              ) : (
                <Stack direction="block" gap="100">
                  {activeTab.items.map((item) => (
                    <Stack
                      key={item.id}
                      direction="inline"
                      gap="100"
                      alignItems="center"
                    >
                      <Box inlineSize="150px">
                        <Text variant="body">{item.product_name}</Text>
                      </Box>
                      <Box inlineSize="60px">
                        <Text variant="body">×{item.quantity}</Text>
                      </Box>
                      <Box inlineSize="80px">
                        <Text variant="captionMedium">€{item.unit_price}</Text>
                      </Box>
                      <Box inlineSize="80px">
                        <Text variant="body">€{item.line_total}</Text>
                      </Box>
                      <Button
                        title="−"
                        type="basic"
                        onPress={() => handleUpdateQty(item.id, item.quantity - 1)}
                      />
                      <Button
                        title="+"
                        type="basic"
                        onPress={() => handleUpdateQty(item.id, item.quantity + 1)}
                      />
                      <Button
                        title="✕"
                        type="destructive"
                        onPress={() => handleRemoveItem(item.id)}
                      />
                    </Stack>
                  ))}
                </Stack>
              )}
            </ScrollView>

            {/* Running total */}
            <Box padding="200" paddingBlock="200">
              <Text variant="headingSmall">Total: €{activeTab.total}</Text>
            </Box>
          </Box>
        )}

        {/* ── Tab Selection ── */}
        {!activeTab && tables.length > 0 && (
          <Box padding="200">
            <SectionHeader title="Select Table" />
            <Stack direction="block" gap="100">
              {tables.map((table) => (
                <Button
                  key={table.id}
                  title={table.name}
                  type="basic"
                  onPress={() => handleOpenTab(table.id)}
                />
              ))}
            </Stack>
          </Box>
        )}

        {!activeTab && openTabs.length > 0 && (
          <Box padding="200">
            <SectionHeader title="Open Tabs" />
            <Stack direction="block" gap="100">
              {openTabs.map((tab) => (
                <Button
                  key={tab.id}
                  title={`${tab.table_name} (${tab.items.length} items, €${tab.total})`}
                  type="basic"
                  onPress={() => handleSelectTab(tab)}
                />
              ))}
            </Stack>
          </Box>
        )}

        {/* ── Sticky bottom: Send to POS Cart button ── */}
        {activeTab && (
          <Box padding="200" paddingBlock="100">
            <Button
              title={
                activeTab.status === "sent"
                  ? "Already Sent"
                  : `Send to POS Cart (€${activeTab.total})`
              }
              type="primary"
              isDisabled={
                activeTab.items.length === 0 ||
                activeTab.status === "sent"
              }
              onPress={handleSendToCart}
            />
          </Box>
        )}
      </Screen>
    );
  }

  // ── Render: Sending ──
  if (viewState.type === "sending") {
    return (
      <Screen name="TabTracker" title="Tab Tracker" isLoading>
        <ScrollView>
          <Box padding="200">
            <Text variant="body">Sending items to POS cart…</Text>
          </Box>
        </ScrollView>
      </Screen>
    );
  }

  // ── Render: Success ──
  if (viewState.type === "success" && activeTab) {
    return (
      <Screen name="TabTracker" title="Tab Tracker">
        <ScrollView>
          <Box padding="200">
            <Banner
              title="Items sent to cart! ✅"
              variant="confirmation"
              visible
            >
              {`${activeTab.items.length} items (€${activeTab.total}) sent to POS cart. Tap Charge to complete payment.`}
            </Banner>
          </Box>
        </ScrollView>
      </Screen>
    );
  }

  // Fallback
  return (
    <Screen name="TabTracker" title="Tab Tracker">
      <ScrollView>
        <Box padding="200">
          <Text variant="body">Loading…</Text>
        </Box>
      </ScrollView>
    </Screen>
  );
}

export default reactExtension(
  "pos.home.modal.render",
  () => <TabTrackerModal />,
);
