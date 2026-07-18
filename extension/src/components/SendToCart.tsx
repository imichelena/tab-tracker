/**
 * SendToCart — confirmation dialog + Cart API integration.
 *
 * Flow:
 * 1. User taps "Send to POS Cart" → confirmation dialog shown
 * 2. User confirms → clearCart() → addLineItem/addCustomSale per item
 * 3. On success → POST /api/v1/tabs/{id}/send-to-cart (backend record)
 * 4. Show success banner, auto-close modal after 2.5s
 *
 * Error handling:
 * - Per-item failures: skip that item, continue with rest
 * - Cart API errors: show which items failed, keep backend tab open
 * - Retry with exponential backoff for transient failures
 */

import { useState, type ReactElement } from "react";
import {
  Box,
  Button,
  Dialog,
  Stack,
  Text,
  Banner,
  Screen,
} from "@shopify/ui-extensions-react/point-of-sale";
import type { Tab } from "../types/index";
import type { CartApiHandle, SendToCartProgress } from "../hooks/useCartApi";
import { sendItemsToCart } from "../hooks/useCartApi";
import type { ApiClient } from "../api/client";

/** Result of a send-to-cart operation for display purposes */
interface SendToCartResultDisplay {
  success: boolean;
  totalSent: number;
  totalAmount: string;
  failedItems: string[];
}

type SendState =
  | { type: "idle" }
  | { type: "sending" }
  | { type: "success"; result: SendToCartResultDisplay }
  | { type: "error"; message: string; failedItems: string[] }
  | { type: "partial"; progress: SendToCartProgress };

interface SendToCartProps {
  activeTab: Tab;
  cartApi: CartApiHandle;
  backendApi: ApiClient;
  onComplete: () => void;
  onCancel: () => void;
}

export function SendToCartDialog({
  activeTab,
  cartApi,
  backendApi,
  onComplete,
  onCancel,
}: SendToCartProps): ReactElement {
  const [state, setState] = useState<SendState>({ type: "idle" });
  const [showConfirm, setShowConfirm] = useState(true);

  const handleConfirm = async () => {
    setShowConfirm(false);
    setState({ type: "sending" });

    try {
      // 1. Send items to POS cart via Cart API
      const progress = await sendItemsToCart(cartApi, activeTab.items, (p) => {
        setState({ type: "partial", progress: p });
      });

      if (progress.failed.length > 0 && progress.succeeded === 0) {
        // All failed
        setState({
          type: "error",
          message: `Failed to add any items to cart. ${progress.failed[0]?.reason ?? "Unknown error"}`,
          failedItems: progress.failed.map((f) => f.name),
        });
        return;
      }

      // 2. Record transaction in backend (only if at least some items succeeded)
      if (progress.succeeded > 0) {
        await backendApi.sendToCart(activeTab.id);
      }

      // 3. Mark success
      setState({
        type: "success",
        result: {
          success: true,
          totalSent: progress.succeeded,
          totalAmount: activeTab.total,
          failedItems: progress.failed.map((f) => f.name),
        },
      });

      // Auto-close after 2.5s
      setTimeout(() => {
        onComplete();
      }, 2500);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to send items to POS cart";
      setState({ type: "error", message, failedItems: [] });
    }
  };

  // ═══ Confirmation Dialog ═══
  if (showConfirm && state.type === "idle") {
    return (
      <Dialog
        title="Send to POS Cart?"
        content={`Send ${activeTab.items.length} items (€${activeTab.total}) to POS cart? Existing cart items will be cleared.`}
        actionText="Send to Cart"
        secondaryActionText="Cancel"
        showSecondaryAction
        isVisible
        onAction={() => {
          void handleConfirm();
        }}
        onSecondaryAction={onCancel}
        type="default"
      />
    );
  }

  // ═══ Sending / Progress ═══
  if (state.type === "sending" || state.type === "partial") {
    const progress =
      state.type === "partial" ? state.progress : undefined;
    return (
      <Screen name="SendToCart" title="Sending..." isLoading>
        <Box padding="200">
          <Stack direction="block" gap="200" justifyContent="center">
            <Text variant="body">
              Sending items to POS cart…
              {progress
                ? ` (${progress.succeeded}/${progress.processed})`
                : ""}
            </Text>
          </Stack>
        </Box>
      </Screen>
    );
  }

  // ═══ Success ═══
  if (state.type === "success") {
    const { result } = state;
    return (
      <Screen name="SendToCart" title="Done">
        <Box padding="200">
          <Banner
            title="Items sent to cart! ✅"
            variant="confirmation"
            visible
          >
            <Stack direction="block" gap="100">
              <Text variant="body">
                {`${result.totalSent} items (€${result.totalAmount}) sent to POS cart. Tap Charge to complete payment.`}
              </Text>
              {result.failedItems.length > 0 && (
                <Text variant="captionRegular" color="TextCritical">
                  {` ${result.failedItems.length} item(s) could not be added.`}
                </Text>
              )}
            </Stack>
          </Banner>
        </Box>
      </Screen>
    );
  }

  // ═══ Error ═══
  if (state.type === "error") {
    return (
      <Screen name="SendToCart" title="Error">
        <Box padding="200">
          <Banner
            title="Send to Cart Failed"
            variant="error"
            visible
            action="Try Again"
            onPress={() => {
              setShowConfirm(true);
              setState({ type: "idle" });
            }}
          >
            <Stack direction="block" gap="100">
              <Text variant="body">{state.message}</Text>
              {state.failedItems.length > 0 && (
                <Text variant="captionRegular">
                  Failed items: {state.failedItems.join(", ")}
                </Text>
              )}
            </Stack>
          </Banner>
          <Box padding="200" />
          <Button
            title="Back to Tab"
            type="basic"
            onPress={onCancel}
          />
        </Box>
      </Screen>
    );
  }

  return <Box padding="200" />;
}
