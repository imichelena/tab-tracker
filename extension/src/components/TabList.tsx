/**
 * TabList — list of open tabs across all tables.
 * Shows table name, item count, total, and elapsed time.
 * Tap to switch to that tab's TabBill view.
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
import type { Tab, Table } from "../types/index";

interface TabListProps {
  openTabs: Tab[];
  tables: Table[];
  error: string | null;
  onSelectTab: (tab: Tab) => void;
  onOpenNewTab: (tableId: number) => void;
  onDismissError: () => void;
}

/**
 * Format elapsed time in a human-readable way.
 */
function formatElapsed(createdAt: string): string {
  const created = new Date(createdAt);
  const now = new Date();
  const diffMs = now.getTime() - created.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;

  const diffHrs = Math.floor(diffMin / 60);
  const remainingMin = diffMin % 60;
  if (diffHrs < 24) return `${diffHrs}h ${remainingMin}m`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays}d ${diffHrs % 24}h`;
}

export function TabList({
  openTabs,
  tables,
  error,
  onSelectTab,
  onOpenNewTab,
  onDismissError,
}: TabListProps): ReactElement {
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

  return (
    <Box padding="200">
      {/* ═══ Open Tabs ═══ */}
      <SectionHeader title="Open Tabs" />
      <ScrollView>
        {openTabs.length === 0 ? (
          <Box padding="200">
            <Text variant="body" color="TextSubdued">
              No open tabs
            </Text>
          </Box>
        ) : (
          <Stack direction="block" gap="100">
            {openTabs.map((tab) => (
              <Box key={tab.id} padding="100">
                <Button
                  title={`${tab.table_name} — ${tab.items.length} item${tab.items.length !== 1 ? "s" : ""}, €${tab.total}`}
                  type="basic"
                  onPress={() => onSelectTab(tab)}
                />
                <Text variant="captionRegular" color="TextSubdued">
                  Opened {formatElapsed(tab.created_at)}
                </Text>
              </Box>
            ))}
          </Stack>
        )}
      </ScrollView>

      {/* ═══ New Tab ═══ */}
      <Box padding="200" paddingBlock="300">
        <SectionHeader title="Start New Tab" />
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
                onPress={() => onOpenNewTab(table.id)}
              />
            ))}
          </Stack>
        </ScrollView>
      </Box>
    </Box>
  );
}
