/**
 * CategoryBar — horizontal scrollable list of category filter pills.
 * Uses POS Button components for category selection.
 */

import type { ReactElement } from "react";
import { Box, Button, Stack } from "@shopify/ui-extensions-react/point-of-sale";
import type { Category } from "../types/index";

interface CategoryBarProps {
  categories: Category[];
  activeCategory: number | null;
  onSelect: (categoryId: number | null) => void;
}

export function CategoryBar({
  categories,
  activeCategory,
  onSelect,
}: CategoryBarProps): ReactElement {
  return (
    <Box padding="200" paddingBlock="100">
      <Stack direction="inline" gap="100">
        <Button
          title="All"
          type={activeCategory === null ? "primary" : "basic"}
          onPress={() => onSelect(null)}
        />
        {categories.map((cat) => (
          <Button
            key={cat.id}
            title={cat.name}
            type={activeCategory === cat.id ? "primary" : "basic"}
            onPress={() =>
              onSelect(activeCategory === cat.id ? null : cat.id)
            }
          />
        ))}
      </Stack>
    </Box>
  );
}
