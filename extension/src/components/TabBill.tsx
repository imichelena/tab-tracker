/**
 * TabBill — shows the current tab's line items with quantity controls,
 * running total, and empty state. Integrates with the product selection
 * panel and the send-to-cart flow.
 */

import type { ReactElement } from "react";
import {
  Box,
  Button,
  ScrollView,
  SectionHeader,
  Stack,
  Text,
  Banner,
} from "@shopify/ui-extensions-react/point-of-sale";
import type { Tab, TabItem, Table } from "../types/index";

interface TabBillProps {
  activeTab: Tab | null;
  tables: Table[];
  loading: boolean;
  error: string | null;
  onOpenTab: (tableId: number) => void;
  onUpdateQty: (itemId: number, qty: number) => void;
  onRemoveItem: (itemId: number) => void;
  onSendToCart: () => void;
  onBackToTabList: () => void;
  onDismissError: () => void;
}

export function TabBill({
  activeTab,
  tables,
  loading,
  error,
  onOpenTab,
  onUpdateQty,
  onRemoveItem,
  onSendToCart,
  onBackToTabList,
  onDismissError,
}: TabBillProps): ReactElement {
  // ═══ Error Banner ═══
  if (error) {
    return (
      <Box padding="200">
        <Banner
          title="Error"
          variant="error"
          visible
          action="Dismiss"
          onPress={onDismissError}
        >
          {error}
        </Banner>
      </Box>
    );
  }

  // ═══ No tab selected — show table selector ═══
  if (!activeTab) {
    return (
      <Box padding="200">
        <SectionHeader title="Select a Table" />
        <ScrollView>
          <Stack direction="block" gap="100">
            {tables.length === 0 && (
              <Text variant="body" color="TextSubdued">
                No tables available
              </Text>
            )}
            {tables.map((table) => (
              <Button
                key={table.id}
                title={table.name}
                type="basic"
                onPress={() => onOpenTab(table.id)}
              />
            ))}
          </Stack>
        </ScrollView>
      </Box>
    );
  }

  // ═══ Loading ═══
  if (loading) {
    return (
      <Box padding="200">
        <Stack direction="block" justifyContent="center" gap="200">
          <Text variant="body">Updating…</Text>
        </Stack>
      </Box>
    );
  }

  // ═══ Tab sent — show status ═══
  if (activeTab.status === "sent") {
    return (
      <Box padding="200">
        <Banner
          title="Tab already sent"
          variant="information"
          visible
          action="Back"
          onPress={onBackToTabList}
        >
          {activeTab.items.length} items (€{activeTab.total}) were already
          sent to POS cart at {activeTab.pos_cart_sent_at ?? "unknown time"}.
        </Banner>
      </Box>
    );
  }

  // ═══ Active tab with items ═══
  const isSendDisabled = activeTab.items.length === 0;

  return (
    <Box padding="200" paddingBlock="100">
      {/* ── Header ── */}
      <SectionHeader
        title={`Tab: ${activeTab.table_name}`}
        action={{
          label: "Switch Table",
          onPress: onBackToTabList,
        }}
      />

      {/* ── Items ── */}
      <ScrollView>
        {activeTab.items.length === 0 ? (
          <Box padding="200">
            <Text variant="body" color="TextSubdued">
              No items yet — tap a product above to add
            </Text>
          </Box>
        ) : (
          <Stack direction="block" gap="100">
            {/* Header row */}
            <Stack direction="inline" gap="100" alignItems="center">
              <Box inlineSize="120px">
                <Text variant="captionMedium">Item</Text>
              </Box>
              <Box inlineSize="50px">
                <Text variant="captionMedium">Qty</Text>
              </Box>
              <Box inlineSize="70px">
                <Text variant="captionMedium">Price</Text>
              </Box>
              <Box inlineSize="70px">
                <Text variant="captionMedium">Total</Text>
              </Box>
              <Box inlineSize="80px" />
            </Stack>

            {activeTab.items.map((item: TabItem) => (
              <Stack
                key={item.id}
                direction="inline"
                gap="100"
                alignItems="center"
              >
                <Box inlineSize="120px">
                  <Text variant="body">
                    {item.product_name}
                  </Text>
                </Box>
                <Box inlineSize="50px">
                  <Text variant="body">×{item.quantity}</Text>
                </Box>
                <Box inlineSize="70px">
                  <Text variant="captionMedium">
                    €{item.override_price ?? item.unit_price}
                  </Text>
                </Box>
                <Box inlineSize="70px">
                  <Text variant="body">€{item.line_total}</Text>
                </Box>
                <Box inlineSize="80px">
                  <Stack direction="inline" gap="025">
                    <Button
                      title="−"
                      type="basic"
                      onPress={() =>
                        onUpdateQty(item.id, item.quantity - 1)
                      }
                    />
                    <Button
                      title="+"
                      type="basic"
                      onPress={() =>
                        onUpdateQty(item.id, item.quantity + 1)
                      }
                    />
                    <Button
                      title="✕"
                      type="destructive"
                      onPress={() => onRemoveItem(item.id)}
                    />
                  </Stack>
                </Box>
              </Stack>
            ))}
          </Stack>
        )}
      </ScrollView>

      {/* ── Running Total ── */}
      <Box padding="200" paddingBlock="200">
        <Stack direction="inline" gap="100" justifyContent="space-between">
          <Text variant="headingSmall">Total</Text>
          <Text variant="headingLarge">€{activeTab.total}</Text>
        </Stack>
      </Box>

      {/* ── Send to Cart Button ── */}
      <Box padding="200" paddingBlock="100">
        <Button
          title={
            isSendDisabled
              ? "Cart is empty"
              : `Send to POS Cart (€${activeTab.total})`
          }
          type="primary"
          isDisabled={isSendDisabled}
          onPress={onSendToCart}
        />
      </Box>
    </Box>
  );
}
