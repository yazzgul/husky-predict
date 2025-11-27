
import React from "react";
import { useNavigate } from "react-router-dom";
import { Accordion, AccordionPanel, Avatar, Button, Heading } from "grommet";

import { convertHuskyUrl } from "../../utils/fieldConverters";
import { ShowOnPedigreePanelContent } from "./ShowOnPedigreePanelContent";
import { DogAttributesList } from "./DogAttributesList";

export const ManageTree = ({
                             currentNode,
                             visibleAttribute,
                             setVisibleAttribute,
                             radioOptions,
                           }) => {
  const navigate = useNavigate();

  return (
      <div className="flex flex-grow flex-shrink basis-0 p-2.5">
        <div className="flex flex-col gap-2 h-min w-full">
          {/* Заголовок с аватаркой */}
          <Heading level="1" size="small" className="mt-2 mb-2">
            Родословная (выбранная собака)
          </Heading>
          {/* Детали собаки */}
          <div className="w-full flex-grow-0 flex-shrink-0">
            <div
                className="flex flex-row gap-2.5 items-center w-full flex-grow-0 flex-shrink cursor-pointer hover:bg-gray-50 rounded p-1 transition-colors"
                onClick={() => {
                  if (currentNode?.id) {
                    navigate(`/dog/${currentNode.id}`);
                    window.scrollTo(0, 0);
                  }
                }}
            >
              <Avatar
                  round="large"
                  background="accent-1"
                  src={
                    currentNode.photo_url
                        ? convertHuskyUrl(currentNode.photo_url.split(";")[0])
                        : "https://placehold.co/600x400?text=No+Image"
                  }
                  imageProps={{ fit: "cover" }}
                  onError={(e) =>
                      (e.target.src = "https://placehold.co/600x400?text=No+Image")
                  }
              />
              <Heading level="2" size="medium" margin="none">
                {currentNode?.registered_name}
              </Heading>
            </div>

            <DogAttributesList currentNode={currentNode} />
            <Button
                className="moveFocusButton"
                onClick={() =>
                    document.getElementsByClassName("currentlySelected")[0].focus()
                }
                label="Переместить фокус на дерево"
                plain={true}
            />
          </div>

          {/* Аккордеон с настройками */}
          <div className="flex flex-col flex-grow flex-shrink-0 justify-end">
            <Accordion multiple>
              <AccordionPanel
                  label={
                    <Heading level="2" size="small" className="mt-2 mb-2">
                      Выберите атрибуты для отображения
                    </Heading>
                  }
              >
                <div className="mb-4">
                  <ShowOnPedigreePanelContent
                      visibleAttribute={visibleAttribute}
                      setVisibleAttribute={setVisibleAttribute}
                      radioOptions={radioOptions}
                  />
                </div>
              </AccordionPanel>
            </Accordion>
          </div>
        </div>
      </div>
  );
};

export default ManageTree;
