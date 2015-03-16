% include('templates/header.tpl', title='Series',
%         stylesheets=('series-index.css', ))
% import urllib
% def uri(str):
%     return urllib.quote_plus(str)
% end

% if len(series) > 0:
<table class="table table-condensed table-striped">
    <tr>
        <th colspan="2">Status</th>
        <th>Subject</th>
        <th>Author</th>
        <th>Age</th>
    </tr>
    % for s in series:
        <tr>
            <td>
                %if s.get('reviewed'):
                    <span title="Reviewers: {{", ".join([x for x, y in s['reviewers']])}}" class="label label-success">Reviewed</span>
                %elif s.get('repliers'):
                    <span title="Have replies from: {{", ".join([x for x, y in s['repliers']])}}" class="label label-info">Replied</span>
                %end
            </td>
            <td class="series-status">
                %if s.get('merged'):
                    <a href="/testing/log/{{uri(s['message-id'])}}">
                        <span title="{{s['testing-end-time']}}" class="label label-primary timestamp">Merged</span>
                    </a>
                %elif s.get('obsoleted-by'):
                    <a href="/series/{{uri(s['obsoleted-by'])}}">
                        <span title="There is a new version, click to see: {{s['obsoleted-by-subject']}}" class="label label-default">Old version</span>
                    </a>
                %elif s.get('testing-started'):
                    <span title="{{s['testing-start-time']}}" class="label label-default timestamp">Testing</span>
                %elif s['testing-passed'] == True:
                    %if s['testing-has-warning']:
                    <a href="/testing/log/{{uri(s['message-id'])}}">
                        <span title="{{s['testing-end-time']}}" class="label label-warning timestamp">Warning</span>
                    </a>
                    %else:
                    <a href="/testing/log/{{uri(s['message-id'])}}">
                        <span title="{{s['testing-end-time']}}" class="label label-success timestamp">Pass</span>
                    </a>
                    %end
                %elif s['testing-passed'] == False:
                    <a href="/testing/log/{{uri(s['message-id'])}}">
                        <span title="{{s['testing-end-time']}}" class="label label-danger timestamp">Failed {{s['testing-failure-step']}}</span>
                    </a>
                %end
            </td>
            <td>
                <a id="{{s['message-id']}}" href="/series/{{uri(s['message-id'])}}">{{s['subject']}}</a>
            </td>
            <td><span title="{{s['author-address']}}">{{s['author']}}</span></td>
            <td><span class="timestamp" title="{{s['date']}}">{{s['age']}}</span></td>
        </tr>
    %end
</table>

% else:
    <div id="message">
      <p>No patches found.</p>
      <div class="frownie">:(</div>
    </div>
%end

<nav>
    <ul class="pagination">
        %dot = True
        %for i in range(0, totalpages):
            % between = lambda v, s, e: v >= s and v <= e
            % show = between(i, 0, 9)
            % show = show or between(i, totalpages - 5, totalpages - 1)
            % show = show or between(i, curpage - 2, curpage + 3)
            % if show:
                <li class="{{"active" if curpage == i else ""}}">
                    <a href="/index/{{i * pagesize}}-{{(i + 1) * pagesize}}{{"?search="+search if search else ""}}">{{i + 1}}</a>
                </li>
                %dot = True
            %elif dot:
                <li class="disabled">
                    <a href="#">...</a>
                </li>
                %dot = False
            %end
        %end
    </ul>
</nav>


<script type="text/javascript">

function main() {
    $(".timestamp").each(function (i, o) {
        $(o).attr("title", new Date(1000 * $(o).attr("title")));
    });
}

$(main);

</script>
% include('templates/footer.tpl')
