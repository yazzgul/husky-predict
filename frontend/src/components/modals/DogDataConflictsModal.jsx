import React, { useState } from "react";

const getFieldLabel = (field) => {
    // Optionally, map field names to user-friendly labels
    return field;
};

export const DogDataConflictsModal = ({
                                          open,
                                          onClose,
                                          conflicts,
                                          onSave,
                                          loading,
                                      }) => {
    const [selected, setSelected] = useState({});
    const [customValues, setCustomValues] = useState({});
    console.log(selected);
    console.log(customValues);
    if (!open) return null;
    if (!conflicts || Object.keys(conflicts).length === 0) return null;

    const handleRadioChange = (field, source, value) => {
        if (source === "other") {
            setSelected((prev) => ({ ...prev, [field]: "other" }));
        } else {
            setSelected((prev) => ({ ...prev, [field]: value }));
            setCustomValues((prev) => {
                const copy = { ...prev };
                delete copy[field];
                return copy;
            });
        }
    };

    const handleCustomChange = (field, value) => {
        setCustomValues((prev) => ({ ...prev, [field]: value }));
    };

    const handleReset = () => {
        setSelected({});
        setCustomValues({});
    };

    const allResolved = Object.keys(conflicts).every((field) => {
        if (selected[field] === "other") {
            return customValues[field] && customValues[field].trim() !== "";
        }
        return selected[field];
    });

    const handleSave = () => {
        if (!allResolved) return;

        // Prepare resolved fields, using custom values for "other" selections
        const resolvedFields = {};
        Object.keys(conflicts).forEach((field) => {
            if (selected[field] === "other") {
                resolvedFields[field] = customValues[field];
            } else {
                resolvedFields[field] = selected[field];
            }
        });

        onSave(resolvedFields);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40">
            <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl p-6 relative max-h-[90vh] flex flex-col">
                <button
                    className="absolute top-4 right-4 text-gray-400 hover:text-gray-600"
                    onClick={onClose}
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="24"
                        height="24"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className="lucide lucide-x"
                    >
                        <path d="M18 6 6 18"></path>
                        <path d="m6 6 12 12"></path>
                    </svg>
                </button>
                <div className="flex items-center mb-4">
                    {/* Merge icon (placeholder) */}
                    <span className="mr-2">🔀</span>
                    <h2 className="text-xl font-bold">Разрешение конфликтов данных</h2>
                </div>
                <div className="flex-1 overflow-y-auto">
                    <div className="space-y-6">
                        {Object.entries(conflicts).map(([field, sources]) => (
                            <div key={field} className="mb-4">
                                <label className="block font-semibold mb-2">
                                    Поле {getFieldLabel(field)}:
                                </label>
                                <div className="space-y-2">
                                    {Object.entries(sources).map(([source, value]) => (
                                        <label
                                            key={source}
                                            className="flex items-center gap-2 cursor-pointer"
                                        >
                                            <input
                                                type="radio"
                                                name={field}
                                                value={value}
                                                checked={selected[field] === value}
                                                onChange={() => handleRadioChange(field, source, value)}
                                                className="w-5 h-5 text-orange-500 bg-gray-100 border-gray-300 cursor-pointer"
                                            />
                                            <span className="text-gray-700">
                        источник {source} - {value}
                      </span>
                                        </label>
                                    ))}
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="radio"
                                            name={field}
                                            value="other"
                                            checked={selected[field] === "other"}
                                            onChange={() => handleRadioChange(field, "other", "")}
                                            className="w-5 h-5 text-orange-500 bg-gray-100 border-gray-300 cursor-pointer"
                                        />
                                        <span className="text-gray-700">другое</span>
                                    </label>
                                    {selected[field] === "other" && (
                                        <div className="ml-7 mt-2">
                                            <input
                                                type="text"
                                                className="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
                                                value={customValues[field] || ""}
                                                onChange={(e) =>
                                                    handleCustomChange(field, e.target.value)
                                                }
                                                placeholder="Введите значение"
                                            />
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="flex justify-end gap-2 mt-6 pt-4 border-t">
                    <button
                        className="px-4 py-2 rounded bg-gray-200 hover:bg-gray-300 text-gray-800"
                        onClick={handleReset}
                        disabled={loading}
                    >
                        Сбросить
                    </button>
                    <button
                        className={`px-4 py-2 rounded text-white ${
                            allResolved
                                ? "bg-blue-600 hover:bg-blue-700"
                                : "bg-blue-300 cursor-not-allowed"
                        }`}
                        onClick={handleSave}
                        disabled={!allResolved || loading}
                    >
                        {loading ? "Сохранение..." : "Сохранить"}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default DogDataConflictsModal;