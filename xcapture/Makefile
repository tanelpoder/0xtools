.PHONY: all clean cleanx check

BUILD_DIR ?= build
TARGET ?= xcapture

all:
	@[ -d $(BUILD_DIR) ] || cmake -S . -B $(BUILD_DIR) >/dev/null
	cmake --build $(BUILD_DIR) --target $(TARGET)

clean:
	rm -rf $(BUILD_DIR)

cleanx:
	@[ -d $(BUILD_DIR) ] && find $(BUILD_DIR) -name 'xcapture' -delete || true
	@[ -d $(BUILD_DIR)/CMakeFiles/xcapture.dir ] && \
		find $(BUILD_DIR)/CMakeFiles/xcapture.dir -type f \( -name '*.o' -o -name '*.o.d' \) -delete || true

check:
	scripts/lint.sh
