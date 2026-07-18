/** Product as returned by GET /api/v1/products */
export interface Product {
  id: number;
  name: string;
  price: string;
  category_id: number;
  category_name: string;
  shopify_variant_id: number | null;
  image_path: string | null;
  override_price: string | null;
}

/** Category as returned by GET /api/v1/categories */
export interface Category {
  id: number;
  name: string;
  sort_order: number;
}

/** Table as returned by GET /api/v1/tables */
export interface Table {
  id: number;
  name: string;
}

/** A single item on a tab */
export interface TabItem {
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

/** Tab state */
export type TabStatus = "open" | "sent" | "closed";

/** Tab as returned by GET /api/v1/tabs */
export interface Tab {
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

/** Transaction record (created by send-to-cart) */
export interface Transaction {
  id: number;
  tab_id: number;
  table_name: string;
  total: string;
  checkout_method: "pos_extension" | "draft_order";
  pos_order_id: string | null;
  pos_terminal_id: string | null;
  created_at: string;
}

/** Cart item representation for Cart API calls */
export interface CartItem {
  variantId?: number;
  title: string;
  price: string;
  quantity: number;
  taxable: boolean;
  isCustomSale: boolean;
}

/** Result of a send-to-cart operation */
export interface SendToCartResult {
  success: boolean;
  transactionId?: number;
  failedItems: string[];
  totalSent: number;
  totalAmount: string;
}

/** API error shape */
export interface ApiError {
  status: number;
  message: string;
  details?: string;
}
