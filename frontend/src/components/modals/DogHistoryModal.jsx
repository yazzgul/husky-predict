import React, { useState } from "react";

const formatDate = (dateString) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return date.toLocaleString("ru-RU");
};

// Helper function to filter out unchanged values
const getChangedValues = (oldValues, newValues) => {
    if (!oldValues || !newValues) return {};

    const changed = {};
    Object.keys(newValues).forEach((key) => {
        if (oldValues[key] !== newValues[key]) {
            changed[key] = {
                old: oldValues[key],
                new: newValues[key],
            };
        }
    });
    return changed;
};

const Accordion = ({ title, children }) => {
    const [open, setOpen] = useState(false);
    return (
        <div className="mb-2 border rounded">
            <button
                className="w-full text-left px-4 py-2 font-semibold bg-gray-100 hover:bg-gray-200"
                onClick={() => setOpen((o) => !o)}
            >
                {title} {open ? "▲" : "▼"}
            </button>
            {open && <div className="px-4 py-2 bg-white">{children}</div>}
        </div>
    );
};

export const DogHistoryModal = ({
                                    open,
                                    onClose,
                                    mergeLogs,
                                    onUndo,
                                    loading,
                                }) => {
    const [selectedLog, setSelectedLog] = useState(null);

    if (!open) return null;
    if (!mergeLogs || mergeLogs.length === 0) return null;

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
                    {/* History icon (placeholder) */}
                    <span className="mr-2">🕓</span>
                    <h2 className="text-xl font-bold">История изменений</h2>
                </div>
                <div className="flex-1 overflow-y-auto">
                    {!selectedLog ? (
                        <div className="space-y-2">
                            {mergeLogs.map((log) => (
                                <button
                                    key={log.id}
                                    className="w-full text-left px-4 py-2 border rounded hover:bg-gray-100 flex justify-between items-center"
                                    onClick={() => setSelectedLog(log)}
                                >
                                    <span>ID: {log.id}</span>
                                    <span className="text-gray-500 text-sm">
                    {formatDate(log.resolved_date)}
                  </span>
                                </button>
                            ))}
                        </div>
                    ) : (
                        <div>
                            <div className="mb-4">
                                <span className="font-semibold">ID:</span> {selectedLog.id}
                                <br />
                                <span className="font-semibold">Дата:</span>{" "}
                                {formatDate(selectedLog.resolved_date)}
                            </div>
                            <Accordion title="Изменённые значения">
                                {(() => {
                                    const changedValues = getChangedValues(
                                        selectedLog.old_values,
                                        selectedLog.new_values
                                    );
                                    if (Object.keys(changedValues).length === 0) {
                                        return <p className="text-gray-500">Нет изменений</p>;
                                    }
                                    return (
                                        <div className="space-y-2">
                                            {Object.entries(changedValues).map(([field, values]) => (
                                                <div
                                                    key={field}
                                                    className="border-l-4 border-blue-500 pl-3"
                                                >
                                                    <div className="font-semibold text-gray-800">
                                                        {field}:
                                                    </div>
                                                    <div className="text-sm">
                            <span className="text-red-600">
                              Было: {values.old}
                            </span>
                                                        <br />
                                                        <span className="text-green-600">
                              Стало: {values.new}
                            </span>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    );
                                })()}
                            </Accordion>
                            <Accordion title="Конфликты">
                <pre className="whitespace-pre-wrap break-all">
                  {JSON.stringify(selectedLog.conflicts, null, 2)}
                </pre>
                            </Accordion>
                        </div>
                    )}
                </div>
                {selectedLog && (
                    <div className="flex justify-end items-center gap-4 mt-6 pt-4 border-t">
                        <button
                            className="px-2 py-2 flex items-center bg-gray-200 rounded hover:bg-gray-300"
                            onClick={() => setSelectedLog(null)}
                        >
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                width="20"
                                height="20"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                strokeWidth="2"
                                className="mr-1"
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M15 19l-7-7 7-7"
                                />
                            </svg>
                            Назад
                        </button>
                        <button
                            className="px-4 py-2 rounded bg-red-600 hover:bg-red-700 text-white"
                            onClick={() => onUndo(selectedLog.id)}
                            disabled={loading}
                        >
                            {loading ? "Откат..." : "Отменить слияние"}
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default DogHistoryModal;