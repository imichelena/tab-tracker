/**
 * useCartApi — typed wrapper around the Shopify POS Cart API.
 *
 * Accessed via api.cart from the POS extension context.
 * Methods: clearCart, addLineItem, addCustomSale, applyCartDiscount, setCustomer.
 */

import { useCallback } from "react";
import type { TabItem } from "../types/index";

/**
 * Result of a send-to-cart operation.
 * Track which items succeeded and which failed.
 */
export interface SendToCartProgress {
  /** Total items processed */
  processed: number;
  /** Items that were sent successfully */
  succeeded: number;
  /** Items that failed (with error messages) */
  failed: { name: string; reason: string }[];
  /** Whether the operation is complete */
  complete: boolean;
}

export interface CartApiHandle {
  clearCart: () => Promise<void>;
  addLineItem: (variantId: number, quantity: number) => Promise<string>;
  addCustomSale: (sale: {
    title: string;
    price: string;
    quantity: number;
    taxable: boolean;
  }) => Promise<string>;
}

/**
 * Perform the full send-to-cart flow.
 *
 * Steps:
 * 1. clearCart()
 * 2. For each tab item:
 *    - If has shopify_variant_id AND no override_price → addLineItem
 *    - Otherwise → addCustomSale (with title, price, qty, taxable)
 * 3. Return a SendToCartProgress object
 *
 * @param cartApi — the POS Cart API handle
 * @param items — tab items to send
 * @param onProgress — optional callback fired after each item
 */
export async function sendItemsToCart(
  cartApi: CartApiHandle,
  items: TabItem[],
  onProgress?: (progress: SendToCartProgress) => void,
): Promise<SendToCartProgress> {
  const progress: SendToCartProgress = {
    processed: 0,
    succeeded: 0,
    failed: [],
    complete: false,
  };

  // 1. Clear cart
  try {
    await cartApi.clearCart();
  } catch (err) {
    const reason = err instanceof Error ? err.message : "Failed to clear cart";
    progress.failed.push({ name: "(clear cart)", reason });
    progress.complete = true;
    onProgress?.({ ...progress });
    return progress;
  }

  // 2. Add each item
  for (const item of items) {
    progress.processed++;

    try {
      if (
        item.shopify_variant_id != null &&
        (item.override_price == null ||
          item.override_price === item.unit_price)
      ) {
        // Standard item with variant — use addLineItem
        await cartApi.addLineItem(item.shopify_variant_id, item.quantity);
      } else {
        // Price-overridden or no variant — use addCustomSale
        const displayPrice =
          item.override_price && item.override_price !== item.unit_price
            ? item.override_price
            : item.unit_price;

        await cartApi.addCustomSale({
          title: item.product_name,
          price: displayPrice,
          quantity: item.quantity,
          taxable: true,
        });
      }

      progress.succeeded++;
    } catch (err) {
      const reason =
        err instanceof Error
          ? err.message
          : `Failed to add "${item.product_name}"`;
      progress.failed.push({ name: item.product_name, reason });
    }

    onProgress?.({ ...progress });
  }

  progress.complete = true;
  onProgress?.({ ...progress });

  return progress;
}

/**
 * React hook wrapper for sendItemsToCart.
 * Returns a callback that performs the full flow.
 */
export function useCartApi() {
  const sendToCart = useCallback(
    async (
      cartApi: CartApiHandle,
      items: TabItem[],
      onProgress?: (progress: SendToCartProgress) => void,
    ): Promise<SendToCartProgress> => {
      return sendItemsToCart(cartApi, items, onProgress);
    },
    [],
  );

  return { sendToCart };
}
