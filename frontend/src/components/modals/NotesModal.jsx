import React from "react";

export const NotesModal = ({ open, onClose, dog }) => {
    if (!open) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40">
            <div className="bg-white rounded-lg shadow-lg w-full max-w-lg p-6 pr-4 pl-4 relative">
                <button
                    className="absolute top-6 right-4 text-gray-400 hover:text-gray-600"
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
                    >
                        <path d="M18 6 6 18"></path>
                        <path d="m6 6 12 12"></path>
                    </svg>
                </button>
                <h2 className="text-xl font-bold mb-4">
                    Заметки и корректировки данных
                </h2>
                {dog.notes && (
                    <div className="mb-4">
                        <h3 className="font-semibold text-gray-700 mb-1">Заметки</h3>
                        <div className="bg-gray-50 rounded p-2 text-gray-800 whitespace-pre-line">
                            {dog.notes}
                        </div>
                    </div>
                )}
                {dog.data_correctness_notes && (
                    <div>
                        <h3 className="font-semibold text-gray-700 mb-1">
                            Корректность данных
                        </h3>
                        <div className="bg-gray-50 rounded p-2 text-gray-800 whitespace-pre-line">
                            {dog.data_correctness_notes}
                        </div>
                    </div>
                )}
                {!(dog.notes || dog.data_correctness_notes) && (
                    <div className="text-gray-500">
                        Нет заметок или информации о корректности данных
                    </div>
                )}
            </div>
        </div>
    );
};

export default NotesModal;