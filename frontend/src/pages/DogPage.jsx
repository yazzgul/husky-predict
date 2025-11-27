
import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { Box, Spinner } from "grommet";

import { PedigreeTree } from "../components/PedigreeTree";
import { ManageTree } from "../components/ManageTree";
import { radioOptions, BACKEND_API_HOST } from "../constants";

export const DogPage = () => {
  const { dogId } = useParams();
  const navigate = useNavigate();

  const [currentDog, setCurrentDog] = useState(null);
  const [pedigreeData, setPedigreeData] = useState(null);
  const [visibleAttribute, setVisibleAttribute] = useState(radioOptions[0]);

  // Форматирование даты
  const formatDate = (dateString) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US");
  };

  // Преобразование структуры данных
  const transformDogStructure = (dog) => ({
    name: dog.registered_name,
    attributes: {
      sex: dog.sex === 1 ? "Male" : "Female",
      color: dog.color,
      birthday: formatDate(dog.date_of_birth),
      registrationNum: dog.registration_number,
      // dnaInfo: dog.dna_info || "N/A",
      // chicNum: dog.chic_num || "N/A",
      // hips: dog.hips || "N/A",
      // ofaLink: dog.ofa_link || "N/A",
    },
    id: dog.id,
    children: [],
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        // const [dogResponse, pedigreeResponse] = await Promise.all([
        //   axios.get(`${BACKEND_API_HOST}/dogs/${dogId}`),
        //   axios.get(`${BACKEND_API_HOST}/pedigree/${dogId}`),
        // ]);

        // Преобразование данных основной собаки

        const pedigreeResponse = await axios.get(
            `${BACKEND_API_HOST}/pedigree/${dogId}`
        );

        const transformedDog = transformDogStructure(pedigreeResponse.data);
        setCurrentDog(transformedDog);

        // Рекурсивное преобразование родословной
        const transformPedigree = (dog) => {
          if (!dog) return null;
          return {
            ...transformDogStructure(dog),
            children: [
              ...(dog.dam ? [transformPedigree(dog.dam)] : []),
              ...(dog.sire ? [transformPedigree(dog.sire)] : []),
            ],
          };
        };

        const transformedPedigreeData = transformPedigree(
            pedigreeResponse.data
        );

        setPedigreeData(transformedPedigreeData);
      } catch (error) {
        console.error("Error fetching dog data:", error);
        navigate("/");
      }
    };

    fetchData();
  }, [dogId, navigate]);

  if (!pedigreeData) {
    return (
        <Box fill align="center" justify="center">
          <Spinner size="large" />
        </Box>
    );
  }

  return (
      <>
        <ManageTree
            currentNode={currentDog}
            visibleAttribute={visibleAttribute}
            setVisibleAttribute={(attributeObj) =>
                setVisibleAttribute(attributeObj)
            }
            radioOptions={radioOptions}
        />
        <PedigreeTree
            pedigree={pedigreeData}
            visibleAttribute={visibleAttribute}
            currentNode={currentDog}
            setCurrentNode={(node) => setCurrentDog(node)}
        />
      </>
  );
};

export default DogPage;
