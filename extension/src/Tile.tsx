import type { ReactElement } from "react";
import { Tile } from "@shopify/ui-extensions-react/point-of-sale";
import type { TileProps } from "@shopify/ui-extensions/point-of-sale";

/**
 * Home screen tile component for the Tab Tracker POS extension.
 *
 * Renders a clickable tile on the POS smart grid that serves as the
 * entry point for the Tab Tracker workflow.
 *
 * @param props - Standard TileProps from @shopify/ui-extensions/point-of-sale
 * @returns A Tile component instance
 */
export function TabTrackerTile(props: TileProps): ReactElement {
  return (
    <Tile
      title={props.title ?? "Tab Tracker"}
      subtitle={props.subtitle}
      badgeValue={props.badgeValue}
      onPress={props.onPress}
      enabled={props.enabled}
    />
  );
}
