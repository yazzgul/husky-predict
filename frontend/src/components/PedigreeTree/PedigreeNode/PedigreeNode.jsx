
import React from "react";
import { Box, Button, Text } from "grommet";

// import { convertHuskyUrl } from "../../../utils/fieldConverters";

function handleKeyPress(e, toggleNode) {
  if (e.key === " ") {
    toggleNode();
  }
  if (e.key === "Enter") {
    document.getElementById("dogDetails").focus();
  }
}

function updateCurrentNode(nodeDatum, setCurrentNode) {
  setCurrentNode(nodeDatum);
}

function getDisplayValue(visibleAttribute, nodeDatum) {
  let label = visibleAttribute.label;
  let value = visibleAttribute.value;
  if (value !== "none") {
    return (
        <Text size="xxlarge">
          {label}: {nodeDatum.attributes[value]}
        </Text>
    );
  }
}

export const PedigreeNode = ({
                               nodeDatum,
                               toggleNode,
                               foreignObjectSize,
                               visibleAttribute,
                               setCurrentNode,
                               currentNode,
                             }) => {
  return (
      <g>
        {/* `foreignObject` requires width & height to be explicitly set. */}
        <foreignObject {...foreignObjectSize}>
          <div
              style={{ height: "93%", width: "97%" }}
              data-xmlns="http://www.w3.org/1999/xhtml"
          >
            <Box
                id="node"
                tabIndex="0"
                onKeyDown={(e) => handleKeyPress(e, toggleNode)}
                onFocus={() => {
                  updateCurrentNode(nodeDatum, setCurrentNode);
                }}
                background="light-2"
                elevation="large"
                fill={true}
                className={
                  nodeDatum.name === currentNode.name ? "currentlySelected" : ""
                }
            >
              <Box flex={true} pad="medium" justify="around">
                <Box align="center" gap="small">
                  {/* <Avatar
                  round="xlarge"
                  background="accent-1"
                  src={
                    currentNode.photo_url
                      ? convertHuskyUrl(currentNode.photo_url)
                      : "https://placehold.co/600x400?text=No+Image"
                  }
                  imageProps={{ fit: "cover" }}
                  onError={(e) =>
                    (e.target.src =
                      "https://placehold.co/600x400?text=No+Image")
                  }
                /> */}
                  <Text size="xxlarge" weight={"bold"}>
                    {nodeDatum.name}
                  </Text>
                  {getDisplayValue(visibleAttribute, nodeDatum)}
                  {nodeDatum.children.length !== 0 && (
                      <div>
                        <Button
                            onClick={(e) => {
                              toggleNode(e);
                            }}
                            tabIndex="-1"
                            label={
                              nodeDatum.__rd3t.collapsed
                                  ? "Show Ancestors"
                                  : "Hide Ancestors"
                            }
                            size="xlarge"
                        />
                      </div>
                  )}
                </Box>
              </Box>
            </Box>
          </div>
        </foreignObject>
      </g>
  );
};

export default PedigreeNode;
