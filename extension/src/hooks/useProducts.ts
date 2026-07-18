/**
 * useProducts — fetch products and categories, manage loading/error state.
 */

import { useState, useEffect, useCallback } from "react";
import type { ApiClient } from "../api/client";
import type { Product, Category } from "../types/index";

export interface UseProductsResult {
  products: Product[];
  categories: Category[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
  /** Returns products filtered by category ID (null = all) */
  getFilteredProducts: (categoryId: number | null) => Product[];
}

export function useProducts(api: ApiClient): UseProductsResult {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [prods, cats] = await Promise.all([
        api.getProducts(),
        api.getCategories(),
      ]);
      setProducts(prods);
      setCategories(cats);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load products";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const getFilteredProducts = useCallback(
    (categoryId: number | null): Product[] => {
      if (categoryId === null) return products;
      return products.filter((p) => p.category_id === categoryId);
    },
    [products],
  );

  return {
    products,
    categories,
    loading,
    error,
    refetch: fetchData,
    getFilteredProducts,
  };
}
