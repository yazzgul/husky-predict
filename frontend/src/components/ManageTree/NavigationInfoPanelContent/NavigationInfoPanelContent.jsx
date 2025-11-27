import { Box, Text } from "grommet";

export const NavigationInfoPanelContent = () => {
    return (
        <Box gap="10px" margin={{ bottom: "medium" }}>
            <Text>
                Нажмите пробел, чтобы показать или скрыть родителей выбранной собаки
            </Text>
            <Text>
                Нажмите Enter, чтобы перейти к деталям выбранной собаки в боковой панели
            </Text>
            <Text>
                При навигации с помощью клавиатуры в конце списка деталей собаки
                появляется ссылка для возврата к дереву
            </Text>
        </Box>
    );
};