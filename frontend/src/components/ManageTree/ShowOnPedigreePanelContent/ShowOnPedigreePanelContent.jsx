import { Box, RadioButtonGroup } from "grommet";

export const ShowOnPedigreePanelContent = ({
                                               visibleAttribute,
                                               setVisibleAttribute,
                                               radioOptions,
                                           }) => {
    return (
        <Box margin={{ bottom: "medium" }}>
            <RadioButtonGroup
                name="Показать на родословной"
                options={radioOptions}
                value={visibleAttribute.value}
                onChange={(e) =>
                    setVisibleAttribute(
                        radioOptions.find((opt) => opt.value === e.target.value)
                    )
                }
            />
        </Box>
    );
};