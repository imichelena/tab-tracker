/**
 * ProductGrid — 2-column grid of product tiles.
 * Each tile shows name, price (override_price if present), and an "Add" button.
 */

import type { ReactElement } from "react";
import {
  Box,
  Button,
  Stack,
  Text,
  Image,
} from "@shopify/ui-extensions-react/point-of-sale";
import type { Product } from "../types/index";

interface ProductGridProps {
  products: Product[];
  onSelect: (product: Product) => void;
}

export function ProductGrid({
  products,
  onSelect,
}: ProductGridProps): ReactElement {
  if (products.length === 0) {
    return (
      <Box padding="200">
        <Text variant="body" color="TextSubdued">
          No products found
        </Text>
      </Box>
    );
  }

  return (
    <Box padding="200">
      <Stack direction="inline" gap="100">
        {products.map((product) => (
          <Box
            key={product.id}
            inlineSize="250px"
            padding="100"
          >
            <Stack direction="block" gap="050">
              {product.image_path ? (
                <Image src={product.image_path} size="m" />
              ) : (
                <Box
                  blockSize="60px"
                  inlineSize="60px"
                  padding="050"
                >
                  <Text variant="captionRegular" color="TextSubdued">
                    No img
                  </Text>
                </Box>
              )}
              <Text variant="body">{product.name}</Text>
              {product.override_price &&
              product.override_price !== product.price ? (
                <Stack direction="inline" gap="025">
                  <Text variant="captionMedium" color="TextSuccess">
                    €{product.override_price}
                  </Text>
                  <Text variant="captionRegular" color="TextSubdued">
                    €{product.price}
                  </Text>
                </Stack>
              ) : (
                <Text variant="captionMedium">€{product.price}</Text>
              )}
              <Button
                title="Add"
                type="primary"
                onPress={() => onSelect(product)}
              />
            </Stack>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}
