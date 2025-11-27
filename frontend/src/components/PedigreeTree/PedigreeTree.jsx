
import React, { useState, useEffect, useRef } from "react";
import Tree from "react-d3-tree";

import { PedigreeNode } from "./PedigreeNode";
import { transformPedigreeStructure } from "../../utils/pedigreeDataConverter";

export const PedigreeTree = ({
                               pedigree,
                               visibleAttribute,
                               currentNode,
                               setCurrentNode,
                             }) => {
  const treeData = transformPedigreeStructure(pedigree);

  const nodeSize = { x: 600, y: 300 };
  const nodePositionX = nodeSize.x / -2;
  const nodePositionY = nodeSize.y / -2;

  const foreignObjectSize = {
    width: nodeSize.x,
    height: nodeSize.y,
    x: nodePositionX,
    y: nodePositionY,
  };

  /**
   * Tracks the size of the tree container.
   *
   * This enables centering of the currently active node.
   */
  const [width, setWidth] = useState();
  const [height, setHeight] = useState();
  const observedDiv = useRef(null);

  const handleElementResized = () => {
    if (observedDiv.current?.offsetWidth !== width) {
      console.log("width is: " + observedDiv.current.offsetWidth);
      setWidth(observedDiv.current.offsetWidth);
    }
    if (observedDiv.current?.offsetHeight !== height) {
      console.log("height is: " + observedDiv.current.offsetHeight);
      setHeight(observedDiv.current.offsetHeight);
    }
  };

  const resizeObserver = new ResizeObserver(handleElementResized);

  useEffect(() => {
    resizeObserver.observe(observedDiv.current);
    return function cleanup() {
      resizeObserver.disconnect();
    };
  });

  /**
   * TODO: change this method so it works with my code
   *
   * Takes a hierarchy point node and centers the node on the screen
   * if the dimensions parameter is passed to the tree. It's a work
   * in progress, and currently prevents the site from compiling.
   *
   * This code is adapted from the react-d3-tree package.
   * Link: https://github.com/bkrem/react-d3-tree/blob/master/src/Tree/index.tsx#L404
   */
  //               = (hierarchyPointNode: HierarchyPointNode<TreeNodeDatum>) => {
  // const centerNode = (hierarchyPointNode) => {
  //   // in the future: change this bool to check the state of a user-controlled toggle
  //   if (true) {
  //     const g = select(`.${this.gInstanceRef}`);
  //     const svg = select(`.${this.svgInstanceRef}`);
  //     const scale = this.state.d3.scale;

  //     // calculate the variables inverted (x->y, y->x) because the orientation is horizontal
  //     let y = -hierarchyPointNode.x * scale + this.props.dimensions.width / 2;
  //     let x = -hierarchyPointNode.y * scale + this.props.dimensions.height / 2;

  //     g.transition()
  //       .duration(800)
  //       .attr('transform', 'translate(' + x + ',' + y + ')scale(' + scale + ')');
  //     // Sets the viewport to the new center so that it does not jump back to original
  //     // coordinates when dragged/zoomed
  //     svg.call(d3zoom().transform, zoomIdentity.translate(x, y).scale(this.props.zoom));
  //   }
  // };

  return (
      // `<Tree />` will fill width/height of its container`.
      <div
          className="w-full bg-gray-30 mt-6 mb-4"
          ref={observedDiv}
          style={{ width: "1200px", height: "850px" }}
      >
        {/* <Box flex={{ grow: 1, shrink: 0 }} basis="0" ref={observedDiv}> */}
        <Tree
            data={treeData}
            initialDepth="4" // comment out for testing
            pathFunc="diagonal"
            depthFactor="700"
            zoom=".25"
            nodeSize={nodeSize}
            collapsible="false" // This prevents nodes from being centered when toggleNode() is called
            dimensions={{ height: height || 500, width: width || "100%" }} // This **should** automatically center the currently focused node, but there's a bug in react-d3-tree
            separation={{ nonSiblings: 1.2, siblings: 1.2 }}
            scaleExtent={{ max: 0.5, min: 0.05 }}
            // translate={{ x: width ? width / 2 : 100, y: 50 }}
            translate={{ x: 100, y: 350 }}
            pathClassFunc={() => "path"}
            renderCustomNodeElement={(rd3tProps) =>
                PedigreeNode({
                  ...rd3tProps,
                  foreignObjectSize,
                  visibleAttribute,
                  setCurrentNode,
                  currentNode,
                })
            }
            // onNodeClick={(node) => handleNodeClick(node.data)}
        />
        {/* </Box> */}
      </div>
  );
};

export default PedigreeTree;
