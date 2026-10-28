# File upload handler
require "sinatra"
require "fileutils"

post "/upload" do
  # BUG 1: no auth check
  file = params["file"]
  filename = file[:filename]

  # BUG 2: path traversal — no sanitization
  path = File.join("uploads", filename)
  File.open(path, "wb") do |f|
    f.write(file[:tempfile].read)
  end

  # BUG 3: no size limit, no type check
  # BUG 4: executable permissions
  FileUtils.chmod(0755, path)

  "Uploaded: #{filename}"
end

get "/read" do
  # BUG 5: arbitrary file read
  path = params["path"]
  File.read(path)
end
