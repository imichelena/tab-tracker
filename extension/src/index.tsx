import type { ReactElement } from "react";
import { reactExtension, Tile } from "@shopify/ui-extensions-react/point-of-sale";

/**
 * Home screen tile for the Tab Tracker POS extension.
 * Renders a clickable tile on the POS smart grid.
 * Tapping the tile opens the full-screen modal (pos.home.modal.render)
 * via shopify.action.presentModal().
 *
 * The modal target is defined in shopify.extension.toml.
 * The extension runtime links the tile to its companion modal automatically;
 * no explicit presentModal() call is needed unless custom orchestration is
 * desired.
 */
function HomeTile(): ReactElement {
  return (
    <Tile
      title="Tab Tracker"
      subtitle="Open tabs"
      onPress={(): void => {
        // The POS extension runtime automatically links the
        // pos.home.tile.render target to pos.home.modal.render
        // when both are defined in shopify.extension.toml.
        // No explicit action needed here for basic tile→modal flow.
      }}
    />
  );
}

export default reactExtension("pos.home.tile.render", () => <HomeTile />);
