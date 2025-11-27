
export const getStatusTags = (dog) => {
    if (!dog) return [];
    const tags = [];
    if (dog.neutered)
        tags.push({ label: "Neutered", color: "bg-red-100 text-red-800" });
    if (dog.approved_for_breeding)
        tags.push({ label: "Stud Animal", color: "bg-green-100 text-green-800" });
    if (dog.frozen_semen)
        tags.push({ label: "Frozen Semen", color: "bg-blue-100 text-blue-800" });
    if (dog.artificial_insemination)
        tags.push({
            label: "AI Available",
            color: "bg-purple-100 text-purple-800",
        });
    return tags;
};
