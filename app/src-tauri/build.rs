//! Build script: Tauri codegen, then Rust protocol types from the JSON Schema.
//!
//! The protocol types are generated into `OUT_DIR` on every build, so they can
//! never drift from `protocol/ev-protocol.schema.json`. Panicking with a clear
//! message is the correct failure mode in a build script.
#![allow(clippy::expect_used)]

use std::{env, fs, path::PathBuf};

use typify::{TypeSpace, TypeSpaceSettings};

const SCHEMA: &str = "../../protocol/ev-protocol.schema.json";

fn main() {
    println!("cargo:rerun-if-changed={SCHEMA}");
    generate_protocol();
    embed_windows_manifest();
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .windows_attributes(tauri_build::WindowsAttributes::new_without_app_manifest()),
    )
    .expect("tauri build");
}

/// Tauri embeds its app manifest only into the app binary, so on Windows the
/// test binaries start without Common Controls v6 and fail at load time
/// (`STATUS_ENTRYPOINT_NOT_FOUND`, seen in CI). The same manifest is embedded
/// through the linker instead, which covers every binary.
fn embed_windows_manifest() {
    let target_os = env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    let target_env = env::var("CARGO_CFG_TARGET_ENV").unwrap_or_default();
    if target_os != "windows" || target_env != "msvc" {
        return;
    }
    let manifest = env::current_dir()
        .expect("build script directory")
        .join("windows-app-manifest.xml");
    println!("cargo:rerun-if-changed={}", manifest.display());
    println!("cargo:rustc-link-arg=/MANIFEST:EMBED");
    println!("cargo:rustc-link-arg=/MANIFESTINPUT:{}", manifest.display());
}

fn generate_protocol() {
    let text = fs::read_to_string(SCHEMA).expect("read protocol schema");
    let schema: schemars::schema::RootSchema =
        serde_json::from_str(&text).expect("parse protocol schema");
    let mut space = TypeSpace::new(TypeSpaceSettings::default().with_struct_builder(false));
    space
        .add_root_schema(schema)
        .expect("convert protocol schema");
    let file: syn::File = syn::parse2(space.to_stream()).expect("parse generated tokens");
    let out = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR")).join("protocol.rs");
    fs::write(out, prettyplease::unparse(&file)).expect("write generated protocol");
}
