import { formatDate } from "./fieldConverters";

export const transformPedigreeStructure = (dog) => {
  if (!dog) return null;
  const originalProps = { ...dog };

  return {
    name: dog.registered_name,
    attributes: {
      sex: dog.sex,
      color: dog.color,
      date_of_birth: formatDate(dog.date_of_birth),
      registration_number: dog.registration_number,
      coi: dog.coi,
    },
    id: dog.id,
    children: [
      ...(dog.dam ? [transformPedigreeStructure(dog.dam)] : []),
      ...(dog.sire ? [transformPedigreeStructure(dog.sire)] : []),
    ],
    originalProps: originalProps,
  };
};

export const reverseTransformPedigreeStructure = (transformedDog) => {
  if (!transformedDog) return null;

  return {
    ...transformedDog.originalProps,
  };
};
