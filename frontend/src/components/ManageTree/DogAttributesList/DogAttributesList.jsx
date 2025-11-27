import { Anchor, Box, NameValueList, NameValuePair } from "grommet";

export const DogAttributesList = ({ currentNode }) => {
  const formatDate = (dateString) => {
    if (!dateString) return "Неизвестно";
    return new Date(dateString).toLocaleDateString();
  };

  return (
      <>
        <NameValueList
            nameProps={{ width: "small" }}
            valueProps={{ width: "small" }}
            margin={{ top: "none", bottom: "xsmall" }}
        >
          <NameValuePair name="Кличка:">
            {currentNode.call_name || "—"}
          </NameValuePair>
          <NameValuePair name="Пол:">
            {currentNode.sex === 1 ? "Мужской" : "Женский"}
          </NameValuePair>
          <NameValuePair name="Окрас:">{currentNode.color || "—"}</NameValuePair>
          <NameValuePair name="Дата рождения:">
            {formatDate(currentNode.date_of_birth)}
          </NameValuePair>
          <NameValuePair name="Рег. №:">
            {currentNode.registration_number || "Н/Д"}
          </NameValuePair>
          <NameValuePair name="Тазобедренные суставы">
            {currentNode.hips || "Н/Д"}
          </NameValuePair>
          <NameValuePair name="CHIC №:">
            {currentNode.chic_num || "Н/Д"}
          </NameValuePair>
          {/* <NameValuePair name="ДНК:">
          {currentNode.dna_info || "Н/Д"}
        </NameValuePair> */}
        </NameValueList>
        {currentNode.ofa_link && (
            <Box>
              <Anchor
                  default
                  href={currentNode.ofa_link}
                  target="_blank"
                  label="Открыть страницу OFA в новой вкладке"
                  margin={{ bottom: "small" }}
              />
            </Box>
        )}
      </>
  );
};

export default DogAttributesList;