
// Форматирование даты
export const formatDate = (dateString, isIncludeTime = false) => {
  if (!dateString) return "Unknown";
  const date = new Date(dateString);

  const dateOptions = {
    year: "numeric",
    month: "long",
    day: "numeric",
  };

  if (isIncludeTime) {
    dateOptions.hour = "2-digit";
    dateOptions.minute = "2-digit";
    dateOptions.hour12 = false; // 24-hour format
  }

  return date.toLocaleDateString("ru-RU", dateOptions);
};

export const convertHuskyUrl = (url) => {
  if (!url) return "";

  return url.replace(/_s\.jpg$/, "_m.jpg");
};
